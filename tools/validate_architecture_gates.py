#!/usr/bin/env python3
"""
TSD §24.1 architecture-enforcement gates (MOD-001, GOV-01-R04).

This slice implements four of the §24.1 gates. Two of them — RLS
lint and permission lint — are the ones `ADR-005` Decision 1 routes to
`veyro-critical-engineer`:

    RLS lint: every tenant table tenant_id NOT NULL + policy + ENABLE/FORCE
    RLS; runtime role cannot own/bypass. Negative isolation tests run with
    production-equivalent role.

    Permission lint: API commands/queries declare action/resource/scope;
    unregistered permission names fail build.

The module dependency/SQL lint (gate 2) below is not a registered
critical slice and is implemented directly in this file.

The other gate names (`screen-contract`,
`domain-uniqueness`, `surface-profile`, `toolchain-qualification`) are
recognised and refused with exit 2 — never a silent PASS for a gate that
does not exist yet.

Outcomes and exit codes (every non-PASS outcome is non-zero):

    0  PASS          the gate inspected real subjects and found no violation
    1  FAIL          at least one named violation
    2  INCONCLUSIVE  nothing to inspect (`*_GATE_VACUOUS`) — an empty scan is
                     not evidence of compliance
    2  ERROR         unusable input (unreadable/unsupported/malformed), or a
                     gate not implemented in this slice

## RLS gate (`--gate rls`) — contract fixed by ADR-010

Inspects the live PostgreSQL catalog of the connected database. The DSN
comes from `VEYRO_RLS_GATE_DSN`, never argv. The inspecting connection needs
no privilege; the verdict is about `--runtime-role`.

Inspector discipline (D2): the first statement pins
`search_path = pg_catalog, pg_temp` and reads it back; everything is then
read in one REPEATABLE READ READ ONLY transaction; afterwards the caller's
search_path is reset. Any unreadable catalog or failed query is ERROR,
never an empty result.

Runtime envelope (D1, allow-by-construction). The runtime closure R is the
runtime role plus every role it is a MEMBER of (SET ROLE counts even with
NOINHERIT); G = R + PUBLIC. Violations are `RLS_RUNTIME_ROLE_ELEVATED` with
a stable detail token:

    ATTRIBUTE:<SUPERUSER|BYPASSRLS|REPLICATION|CREATEROLE|CREATEDB>@<role>   (D1.1)
    PREDEFINED_ROLE:<role>          oid < 16384 or name pg_*, incl.
                                    pg_database_owner                     (D1.2)
    OWNS:<class>:<identity>         pg_shdepend owner rows + datdba/nspowner/
                                    relowner belt-and-braces              (D1.3)
    PRIVILEGE:<class>:<id>:<p>@<g>  any non-system ACL entry for G outside
                                    the allow-table (default deny)        (D1.4)
    SYSTEM_ACL_MODIFIED:<id>:<p>@<g> system-object entry for G not in its
                                    initial ACL (pg_init_privs, else
                                    acldefault)                           (D1.5)
    OUT_OF_SCOPE:<relation>         granted relation outside --schema     (D1.6)
    TENANT_CONTEXT_DEFAULT:<source> persisted app.* setting for G, or a
                                    non-empty inspector app.tenant_id     (D1.7)
    ATTRIBUTE:LO_COMPAT_PRIVILEGES@<db>  lo_compat_privileges on           (D1.4)

Allow-table for G on non-system objects: database CONNECT/TEMPORARY; schema
USAGE; tenant/platform table and view SELECT/INSERT/UPDATE/DELETE (not
PUBLIC); matview SELECT; sequence USAGE/SELECT/UPDATE (not PUBLIC);
function EXECUTE; type/language USAGE; everything else none.

Relations (D4): tenant table = kind r/p with `tenant_id`, which must be
uuid (`RLS_TENANT_ID_NOT_UUID`) and NOT NULL (`RLS_TENANT_ID_NULLABLE`),
with ENABLE + FORCE RLS and at least one policy (`RLS_NOT_ENFORCED`).
Every permissive policy reachable by G must deparse, under the pinned
search_path, to the predicate pinned for the server major
(`PINNED_TENANT_PREDICATES`; only PG16) in USING and effective WITH CHECK,
and its pg_depend rows may reference only its own relation (dependency
closure); otherwise `RLS_NOT_ENFORCED`. An unpinned major is ERROR. Kinds
v/m/f/S are scanned: a granted view needs `security_invoker`; a granted
materialized view must be a manifest `matview` without `tenant_id`; a
granted foreign table is always `RLS_NOT_ENFORCED`. Other r/p tables must
be manifest `table` entries or are `RLS_TABLE_UNCLASSIFIED`. Executable
non-system SECURITY DEFINER functions must be listed in the manifest
(`RLS_SECURITY_DEFINER_UNREVIEWED`).

Manifest (D3): always `backend/migrations/rls-manifest.json`, version 2; no
CLI flag can substitute it. Missing, symlinked, malformed, or with an
approval (`ADR-NNN`/`OWN-NNN`) that does not resolve to exactly one live
record naming the entry is ERROR. Entry/relation mismatches are
`RLS_EXEMPTION_INVALID`. `--require-table` pins tables that must exist; zero
tenant tables in scope is INCONCLUSIVE (`RLS_GATE_VACUOUS`).

Disclosed limits (ADR-010 residuals): one database only; pooled-connection
tenant switching and TEN-002 resolution are the behavioural harness's and
MOD-004's job; ALTER DEFAULT PRIVILEGES is judged only through the objects
it creates; a deliberate tightening of a system ACL can false-FAIL. PG16
records no pg_init_privs rows for information_schema; per ADR-010 A1.3 its
initial ACL is owner acldefault plus an exact per-object PUBLIC pin
(`PINNED_INFORMATION_SCHEMA_SELECT`: schema USAGE and SELECT on 62 named
stock relations with their expected class).

System objects (ADR-010 A1.2): an object in a non-temp `pg_*` or
`information_schema` namespace with oid < 16384, or any object with a
pg_init_privs row. Any other object in those namespaces on which G holds a
privilege is `RLS_RUNTIME_ROLE_ELEVATED NON_STOCK_SYSTEM_OBJECT:<class>:<id>:
<priv>@<grantee>`, with no allow-table and no manifest escape. Temp
namespaces are never system and are judged as ordinary objects.

## Permission gate (`--gate permission`) — contract fixed by ADR-009

Inputs (ADR-009 D1/D2), stdlib JSON only:

* `--openapi-dir` (default `contracts/openapi/`), searched recursively.
  Every file must be a UTF-8 OpenAPI **3.1.x** `.json` document; any other
  file, any symlink, and 3.0/3.2+ are ERROR (only `.gitkeep` is ignored).
  Operation-bearing locations outside `paths` — top-level `webhooks`,
  `components.pathItems`, `components.callbacks`, operation `callbacks` —
  are ERROR, as are `$ref` path items and any path-item key other than the
  eight lowercase methods, summary/description/servers/parameters and
  `x-*`. Duplicate JSON keys and over-deep nesting are ERROR. Across all
  documents a `(method, path template)` (parameter names normalised) or
  an `operationId` may appear once.
* `--registry` (default `contracts/permissions/registry.json`), version 2
  per ADR-010 D5.1:

      {"version": 2, "permissions": {
         "members.profile.read": {"scopes": ["self"], "authentication": "authenticated"},
         "iam.session.create": {"scopes": ["self"], "authentication": "credential_exchange",
                                "justification": "IAM-01 sign-in establishes the principal.",
                                "approval": "ADR-NNN"}}}

  `authentication` is required; any class other than `authenticated`
  requires a non-empty `justification` and an `approval` that resolves to
  one live ADR/OWN record naming the permission. No other keys.

Every operation (ADR-009 D3/D4) carries both

      "x-veyro-permission": {"action": "read", "resource": "members.profile", "scope": "self"}
      "x-veyro-authentication": "authenticated" | "credential_exchange"
                                | "provider_signature" | "anonymous"

The permission `resource + "." + action` must be registered with that
scope; the operation's class must equal the registry entry's class (two-key
match); `security` values must be arrays of {scheme: [strings]} naming
defined, well-formed Security Scheme Objects (otherwise ERROR, ADR-010
D5.2); and native OpenAPI `security` must agree: `authenticated` needs a
non-empty effective requirement with no `{}` and only defined schemes;
`anonymous` needs an explicit `"security": []`; `credential_exchange` and
`provider_signature` must set an explicit array `security` (ERROR if
missing or null) rather than inherit the root. Per-operation failures are `UNREGISTERED_PERMISSION` citing the
endpoint. There is no exemption, skip or allowlist path. Every run lists
each non-`authenticated` operation in `inventory` (text and JSON) with a
count per class.

What this gate does not prove: that served routes equal the committed
contract (ADR-009 "Residual risk"), or runtime enforcement (IAM-002's
runtime half). A PASS means "every operation in the committed contract".

## Module dependency/SQL gate (`--gate module-deps`)

Inputs: `--modules-dir` (default `backend/app/modules/`) and
`--module-manifest` (default `contracts/modules/ownership.json`). Neither
flag offers a skip, exempt, or allowlist path.

Modules root: the dotted package path of `--modules-dir`, derived by
walking parents while `__init__.py` exists (e.g. `backend/app/modules` ->
`app.modules`). Missing, symlinked, not a directory, or no `__init__.py`
is ERROR.

Manifest (version 1): `{"modules": {<name>: {"domain": "COM-01",
"owned_table_prefixes": [...], "owned_schemas": [...], "public_interfaces":
[...]}}}`. `owned_schemas` is optional (default `[]`); the other three
keys are required and no others are accepted. ERROR on a missing/
symlinked/malformed/non-UTF-8/duplicate-key file; a version other than 1;
a module named `_shared`; a malformed or duplicated `domain`; an empty or
malformed `owned_table_prefixes`/`owned_schemas`; a schema owned twice; or
a `public_interfaces` entry that is not a dotted path strictly under that
module's own package, or that does not resolve to an existing `<path>.py`
or `<path>/__init__.py` inside that module's own directory (ADR-011 D2 /
R1-F13 — a typo must narrow the approved import surface, never widen it;
a symlink anywhere on the resolved path is refused). Existence is checked
only for modules whose directory is actually present, so D5.6's
"manifest entry with no directory is only a note" is preserved — such a
module's interfaces go unverified, which is that note's disclosed
consequence.

`owned_table_prefixes` ambiguity (GATE2-ARCHITECTURE-DECISION-2026-10-05.md
Verdict C) is three cases, not one: (1) one module declaring nested
prefixes (`cal_` and `cal_event_`) is ACCEPTED — both resolve to the same
owner, attribution stays unambiguous, and this is the only shape under
which rule 5's "longest matching `owned_table_prefixes`" resolution is
ever a live choice; (2) two *different* modules declaring overlapping
prefixes (one a prefix of the other) is ERROR with no exception path —
attribution would become resolution-order-dependent and could silently
mask a `CROSS_DOMAIN_SQL_IMPORT`; (3) one module declaring the exact same
prefix twice (`["cal_", "cal_"]`) is ERROR as malformed input — a
duplicate carries no ownership information and is never an intentional
declaration, the same rationale already applied to duplicate
`owned_schemas`.

Discovery: a module is an immediate child directory of `--modules-dir`
with `__init__.py`, excluding `__pycache__`, dot-prefixed names and
`_shared`. A discovered module with no manifest entry is ERROR; a
manifest entry with no directory is only a note. `_shared/` is scanned
as domain-free source — it owns no tables. A domain module may import
`_shared`; `_shared` importing a domain module's internals or referencing
its owned table is `CROSS_DOMAIN_SQL_IMPORT` (ADR-011 D4;
`.claude/rules/backend/architecture.md` control 3).

File walk, per module directory and `_shared`, skipping `__pycache__` and
dot-dirs: any symlink is ERROR. `.py` is read as UTF-8 and AST-parsed (a
syntax error is ERROR, never a skip; an unreadable or non-UTF-8 `.py` file is
`MODULE_DEPS_GATE_INPUT_INVALID` ERROR too — including one that is legal
Python under a PEP 263 coding cookie, since the cookie is not honoured — never
an uncaught traceback, ADR-011 D7.3/R1-F07. The `.sql` read goes through the
same single conversion helper and fails closed identically); `.sql` is
read as UTF-8 and scanned as SQL text; `.md`/`.txt`/
`.gitkeep` are inert and only counted; any other extension is ERROR — the
recognised set is deliberately closed.

Modules-root files: direct (non-recursive) files under `--modules-dir`
itself are scanned, not refused, as importer `_root` (ADR-011 D4). A
directory entry there is skipped without descending (module directories
and `_shared` are covered by the discovery/file walk above); any symlink
is ERROR; the same closed `.py`/`.sql`/inert categorisation applies.
`_root` is domain-free: an import of another module's declared
`public_interfaces` is allowed, an import of its internals is
`CROSS_DOMAIN_SQL_IMPORT`, and the TSD §6.3 bidirectional-pair check does
not apply (`_root` has no domain to pair). Because `_root` owns no table,
every attributed table reference from a modules-root file is
`CROSS_DOMAIN_SQL_IMPORT` (a permanent FAIL, not an ERROR) and every
unattributed one is `MODULE_DEPS_TABLE_UNATTRIBUTED`.

Cross-module Python imports resolve to an absolute dotted path (a
relative import is resolved against the file's own package; one that
escapes the root is ERROR). A path outside `--modules-dir` is ignored;
otherwise the next segment is the target module. Importing one's own
module or `_shared` is always allowed. Otherwise: a path that is not the
target's declared `public_interfaces` (or a submodule of one) is
`CROSS_DOMAIN_SQL_IMPORT`, citing both modules, both domains, the
resolved path and `relpath:lineno` — this takes precedence over the TSD
§6.3 bidirectional-pair exception in both directions, since §6.3 only
ever licenses the opposite module's application interface, never its
internals. Otherwise, for one of the four TSD §6.3 pairs
(`BIDIRECTIONAL_PAIRS`, pinned here and never manifest-configurable),
only the one listed synchronous edge is allowed; the reverse is
`REVERSE_EDGE_NOT_EVENT_DRIVEN`, citing the one permitted direction.
Otherwise the import is an approved application interface.

SQL check: a string (`.py` literal or whole `.sql` file) is SQL-ish if it
contains, case-insensitively, one of SELECT/INSERT/UPDATE/DELETE/TRUNCATE
and one of FROM/INTO/JOIN/TABLE/SET. Table identifiers are extracted
per recognised table position (ADR-011 D6.7.2's
`_table_position_results` stream): after FROM/JOIN/INTO/UPDATE/TABLE,
after a REFERENCES target, after a `DELETE ... USING` target, and across
a FROM list's comma-separated elements including their bare or `AS`
aliases. A recognised position that yields no identifier is
`MODULE_DEPS_SOURCE_UNINSPECTABLE` (ERROR) whatever the other positions
in the same statement did. Each extracted identifier is resolved to an
owning module by
`owned_schemas` (schema-qualified) or the longest matching
`owned_table_prefixes` entry (bare); a different owner than the file's
own module is `CROSS_DOMAIN_SQL_IMPORT`. An identifier no module owns is
`MODULE_DEPS_TABLE_UNATTRIBUTED` (ERROR exit 2), and the count of
unattributed identifiers is disclosed in the report note. ADR-011 D6.8
privilege-list narrowing suppresses privilege-name signals from the
position stream when they occupy a positively-computed GRANT/REVOKE
privilege-list region, with suppression count disclosed in the report.

Uninspectable source is ERROR (`MODULE_DEPS_SOURCE_UNINSPECTABLE`, every
instance collected, cited by `relpath:lineno`): a dynamic-import call
(`__import__`, `importlib.import_module`, `importlib.__import__` —
on the literal name `importlib` or on a name the same file bound to the
`importlib` module via `import importlib [as ...]`; either of those two
attributes retrieved through `getattr(<importlib>, ...)`, including a
non-constant attribute argument; a
call of a name the same file bound to `importlib.import_module` via
`from importlib import import_module [as ...]`, or `__import__` on the
stdlib `builtins` module the same file bound via `import builtins
[as ...]`, directly or through `getattr` — R1-F05); a call of the builtin
`exec` (bare name, `<builtins>.exec`, or a `from builtins import exec
[as ...]` binding) whose source argument is not provably import-free,
and a `getattr(<builtins>, "exec")` retrieval, which has no source
argument to prove anything about — an admissible `exec` source is a
string literal whose parsed AST carries no import statement, no
dynamic-import call and no further `exec`; the inspected string is parsed,
never executed (R1-F05); an
f-string with SQL-ish literal parts and an interpolated value; a SQL-ish
literal with a dangling FROM/JOIN/INTO/UPDATE/TABLE keyword (the table
name is concatenated in); or string concatenation (`+`/`%`) with a
SQL-ish operand. Any uninspectable finding reports ERROR directly with
exactly those findings — never folded into a FAIL alongside other
violations the gate cannot fully vouch for in the same run.

Vacuous (`MODULE_DEPS_GATE_VACUOUS`, INCONCLUSIVE): zero substantive
files inspected — a `.py` file is substantive unless its AST body is
nothing but a lone docstring; every `.sql` file is substantive. An empty
scaffold scan is not evidence of compliance.

What this gate does not prove: only statically-resolvable Python imports
and string-literal SQL inside `--modules-dir` are analysed. A table
identifier no declared module owns is not attributed to anyone. SQL that
reaches the database from outside this tree, ORM-reflected or
driver-level dynamic SQL, and any non-Python/non-`.sql` source are out of
scope. Docstring positions (module/class/function `body[0]` `Expr`
`Constant`) are withheld from the SQL scan per ADR-011 D6.4, counted and
disclosed in a note on every run; the residual is that SQL reaching the
database through `__doc__` is examined by nothing, and is NOT covered by
the dynamic-construct rule above, which keys on runtime-assembly shapes
and never on a plain `Constant`. Both `str` and `bytes` literals are
scanned per ADR-011 D6.2 — a `bytes` literal is decoded UTF-8 first then
latin-1, and one no codec can decode is `MODULE_DEPS_SOURCE_UNINSPECTABLE`
ERROR, never a skipped literal; the D6.4 docstring exclusion applies to
`str` only, because Python binds only a `str` `body[0]` to `__doc__`.
This gate's input contract is fixed by ADR-011, including its D6.7 and
D6.8 addenda; gates 1 (RLS) and 4 (permission) have separate contracts.

This tool never writes to anything it inspects.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PASS, FAIL, INCONCLUSIVE, ERROR = "PASS", "FAIL", "INCONCLUSIVE", "ERROR"
EXIT_CODES = {PASS: 0, FAIL: 1, INCONCLUSIVE: 2, ERROR: 2}

IMPLEMENTED_GATES = ("rls", "permission", "module-deps", "event-contract")
DEFERRED_GATES = (
    "screen-contract",
    "domain-uniqueness",
    "surface-profile",
    "toolchain-qualification",
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DSN_ENV = "VEYRO_RLS_GATE_DSN"


@dataclass(frozen=True)
class Violation:
    code: str
    subject: str
    detail: str


@dataclass
class GateReport:
    gate: str
    status: str
    violations: list[Violation] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # permission gate: every non-`authenticated` operation (ADR-009 D4.4)
    inventory: list[dict[str, str]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]

    def codes(self) -> set[str]:
        return {v.code for v in self.violations}

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    def render(self) -> str:
        lines = [f"[{self.gate}] {self.status} — checked {len(self.checked)} subject(s)"]
        lines += [f"  {v.code}: {v.subject} — {v.detail}" for v in self.violations]
        lines += [f"  note: {n}" for n in self.notes]
        lines += [f"  inventory: {r['authentication']}: {r['endpoint']} -> {r['permission']}"
                  f" (approval {r.get('approval') or '-'})" for r in self.inventory]
        return "\n".join(lines)


def _finish(gate: str, violations: list[Violation], checked: list[str], vacuous: str | None,
            notes: list[str]) -> GateReport:
    if violations:
        status = FAIL
    elif vacuous:
        status = INCONCLUSIVE
        code = f"{gate.upper().replace('-', '_')}_GATE_VACUOUS"
        violations = [Violation(code, "-", vacuous)]
    else:
        status = PASS
    return GateReport(gate, status, violations, sorted(checked), notes)


# --- RLS gate (ADR-010) ------------------------------------------------------------

# ADR-010 D4.3: pg_get_expr() deparse, under the D2-pinned search_path, of
#   tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
# per PostgreSQL major. An unpinned major is ERROR, never PASS or FAIL.
CANONICAL_TENANT_PREDICATE = (
    "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
)
PINNED_TENANT_PREDICATES = {16: CANONICAL_TENANT_PREDICATE}
PINNED_SEARCH_PATH = "pg_catalog, pg_temp"  # ADR-010 D2.1
# ADR-010 A1.3 (D1.5a): PostgreSQL 16 records no pg_init_privs rows for
# information_schema, so its initial ACL is owner acldefault plus exactly these
# PUBLIC grants: USAGE on the schema, and SELECT on each named stock relation
# with its expected class (all views except 3 tables). Per object, never per
# class; only applied to system objects (oid < 16384, A1.2) with no
# pg_init_privs row. Anything else on information_schema stays
# SYSTEM_ACL_MODIFIED. Adding a major needs raw pristine-initdb evidence and
# independent security review (A1.3 "Pinning rules").
PINNED_INFORMATION_SCHEMA_SELECT: dict[int, dict[str, str]] = {16: {
    "administrable_role_authorizations": "view", "applicable_roles": "view",
    "attributes": "view", "character_sets": "view", "check_constraint_routine_usage": "view",
    "check_constraints": "view", "collation_character_set_applicability": "view",
    "collations": "view", "column_column_usage": "view", "column_domain_usage": "view",
    "column_options": "view", "column_privileges": "view", "column_udt_usage": "view",
    "columns": "view", "constraint_column_usage": "view", "constraint_table_usage": "view",
    "data_type_privileges": "view", "domain_constraints": "view", "domain_udt_usage": "view",
    "domains": "view", "element_types": "view", "enabled_roles": "view",
    "foreign_data_wrapper_options": "view", "foreign_data_wrappers": "view",
    "foreign_server_options": "view", "foreign_servers": "view", "foreign_table_options": "view",
    "foreign_tables": "view", "information_schema_catalog_name": "view",
    "key_column_usage": "view", "parameters": "view", "referential_constraints": "view",
    "role_column_grants": "view", "role_routine_grants": "view", "role_table_grants": "view",
    "role_udt_grants": "view", "role_usage_grants": "view", "routine_column_usage": "view",
    "routine_privileges": "view", "routine_routine_usage": "view",
    "routine_sequence_usage": "view", "routine_table_usage": "view", "routines": "view",
    "schemata": "view", "sequences": "view", "sql_features": "table",
    "sql_implementation_info": "table", "sql_sizing": "table", "table_constraints": "view",
    "table_privileges": "view", "tables": "view", "triggered_update_columns": "view",
    "triggers": "view", "udt_privileges": "view", "usage_privileges": "view",
    "user_defined_types": "view", "user_mapping_options": "view", "user_mappings": "view",
    "view_column_usage": "view", "view_routine_usage": "view", "view_table_usage": "view",
    "views": "view",
}}
FIRST_NORMAL_OBJECT_ID = 16384  # ADR-010 D1.2
RLS_MANIFEST_PATH = REPO_ROOT / "backend" / "migrations" / "rls-manifest.json"  # ADR-010 D3.1

# ADR-010 D1.4 allow-table: privileges the runtime closure (or PUBLIC) may hold
# on a non-system object, by object class. Anything absent is denied.
_DML = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})
ALLOWED_PRIVILEGES: dict[str, frozenset[str]] = {
    "database": frozenset({"CONNECT", "TEMPORARY"}),
    "schema": frozenset({"USAGE"}),
    "table": _DML,
    "view": _DML,
    "matview": frozenset({"SELECT"}),
    "sequence": frozenset({"USAGE", "SELECT", "UPDATE"}),
    "function": frozenset({"EXECUTE"}),
    "type": frozenset({"USAGE"}),
    "language": frozenset({"USAGE"}),
}
_NO_PUBLIC = frozenset({"table", "view", "sequence"})  # TSD §7.3 / ADR-010 D1.4
_RELKIND_CLASS = {"r": "table", "p": "table", "v": "view", "m": "matview",
                  "f": "foreign_table", "S": "sequence"}
_TRUTHY = frozenset({"true", "on", "yes", "1"})


@dataclass(frozen=True)
class RoleInfo:
    name: str
    oid: int
    superuser: bool = False
    bypassrls: bool = False
    replication: bool = False
    createrole: bool = False
    createdb: bool = False


@dataclass(frozen=True)
class AclGrant:
    """One privilege held by the runtime closure or PUBLIC on one object."""
    obj_class: str
    identity: str
    privilege: str
    grantee: str  # role name, or PUBLIC
    system: bool = False  # A1.2: stock (oid < 16384) in a system namespace, or has init privs
    in_initial: bool = True  # only meaningful for system objects (D1.5)
    relation: str | None = None  # schema.relation for relation/column grants
    schema: str | None = None
    non_stock: bool = False  # A1.2: in a non-temp system namespace but not a system object
    has_init_privs: bool = False


@dataclass(frozen=True)
class Policy:
    name: str
    permissive: bool
    command: str  # pg_policy.polcmd: r=SELECT a=INSERT w=UPDATE d=DELETE *=ALL
    using: str | None
    with_check: str | None
    applies_to_runtime: bool
    foreign_dependencies: tuple[str, ...] = ()  # D4.3 dependency closure


@dataclass(frozen=True)
class Relation:
    schema: str
    name: str
    kind: str  # pg_class.relkind
    has_tenant_id: bool = False
    tenant_id_uuid: bool = False
    tenant_id_not_null: bool = False
    rls_enabled: bool = False
    rls_forced: bool = False
    policies: tuple[Policy, ...] = ()
    security_invoker: bool = False

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass(frozen=True)
class RlsCatalog:
    runtime: str
    runtime_exists: bool
    server_version_num: int
    database: str
    closure: tuple[RoleInfo, ...] = ()
    relations: tuple[Relation, ...] = ()
    grants: tuple[AclGrant, ...] = ()
    owned: tuple[tuple[str, str], ...] = ()  # (class, identity)
    security_definer: tuple[str, ...] = ()  # executable non-system SECURITY DEFINER keys
    tenant_context_defaults: tuple[str, ...] = ()
    lo_compat_privileges: bool = False
    scanned_schemas: tuple[str, ...] = ()
    missing_schemas: tuple[str, ...] = ()


@dataclass(frozen=True)
class RlsManifest:
    platform_scope_relations: Mapping[str, str] = field(default_factory=dict)  # name -> kind
    reviewed_security_definer_functions: frozenset[str] = frozenset()


EMPTY_RLS_MANIFEST = RlsManifest()


class GateInputError(Exception):
    """Unusable gate input -- ADR-011 D7.3's single conversion target for
    `OSError`/`UnicodeDecodeError`/`ValueError`, reported as that gate's
    `*_GATE_INPUT_INVALID` ERROR at exit 2.

    `notes` carries disclosure a partially-completed check had already
    established before it aborted, so the ERROR report it becomes is not
    note-blind: ADR-011 D5.5/D8 require the coverage bucket counts to appear
    in the report on *every* run, and an ERROR run is not exempt. Every
    pre-existing raise site constructs this with a message only and leaves
    `notes` empty, so the attribute is additive. Notes attached here are a
    *lower bound* labelled as such by their producer -- never a complete
    total invented for an enumeration that never finished.
    """

    def __init__(self, *args: Any, notes: Sequence[str] | None = None) -> None:
        super().__init__(*args)
        self.notes: list[str] = list(notes or [])


def _read_gate_text(path: Path, subject: str, what: str) -> str:
    """ADR-011 D7.3's single read/decode conversion point for every *text* file a
    gate opens: `OSError`, `UnicodeDecodeError` and `ValueError` become
    `GateInputError`, which each gate's own handler reports as that gate's
    `*_GATE_INPUT_INVALID` ERROR at exit 2 -- never an uncaught traceback with
    exit 1 and no `GateReport` at all, which is what a bare
    `path.read_text(encoding="utf-8")` produced (R1-F07, reproduced by direct
    execution at every site before its increment). `_load_json` is this helper's
    JSON-shaped sibling and keeps its own conversion, because it must convert the
    *parse* step too; it is the same three exception types plus `RecursionError`.

    `subject` names the input in the message -- a repository-relative path, or an
    approval reference where the path is derived from one. `what` names the file
    class. Both appear with the exception's own type name so that a decode
    failure stays distinguishable from `EACCES` at the same read site, and the
    exception's message is included: every caller passes a repository-local gate
    input, not a connection string (contrast `_rls_from_cli`, which deliberately
    discloses the class name only).
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise GateInputError(
            f"{subject}: cannot read {what} ({type(exc).__name__}: {exc})"
        ) from None


# --- approval resolution (ADR-010 D3.4, shared with ADR-010 D5.1) ------------------

_APPROVAL_RE = re.compile(r"(ADR|OWN)-[0-9]{3}")
_TABLE_RE = re.compile(r"[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*")
_STATUS_RE = re.compile(r"^status:[ \t]*(.*)$", re.MULTILINE)


def resolve_approval(ref: Any, key: str, root: Path) -> None:
    """Raise GateInputError unless `ref` names exactly one live record that
    contains `key` verbatim. Reads only the repository under `root`."""
    if not (isinstance(ref, str) and _APPROVAL_RE.fullmatch(ref)):
        raise GateInputError(f"approval {ref!r} is not ADR-NNN/OWN-NNN")
    if ref.startswith("ADR-"):
        matches = sorted((root / "knowledge" / "04-Decisions").glob(f"{ref}-*.md"))
        if len(matches) != 1:
            raise GateInputError(f"approval {ref}: {len(matches)} matching ADR files, need 1")
        text = _read_gate_text(matches[0], f"approval {ref}", "ADR record")
        front = text.split("\n---", 1)[0] if text.startswith("---\n") else ""
        status = _STATUS_RE.search(front)
        if not status or not status.group(1).startswith(("DECIDED", "ACCEPTED")):
            raise GateInputError(f"approval {ref}: status is not DECIDED/ACCEPTED")
        if key not in text:
            raise GateInputError(f"approval {ref} does not mention {key!r}")
        return
    path = root / "knowledge" / "00-System" / "OWNER_APPROVALS.md"
    # `is_file()` swallows every `OSError` (including `EACCES` on an ancestor), so a
    # false "absent" still reads as "0 matching rows" below -- already fail-closed.
    # The read itself is the D7.3 site: an unreadable or non-UTF-8 register is
    # unusable input, never an empty row set that could clear an approval check.
    text = ""
    if path.is_file():
        text = _read_gate_text(path, f"approval {ref}", "OWNER_APPROVALS register")
    rows = [ln for ln in text.splitlines() if ln.startswith(f"| {ref} |")]
    if len(rows) != 1:
        raise GateInputError(f"approval {ref}: {len(rows)} OWNER_APPROVALS rows, need 1")
    if key not in rows[0]:
        raise GateInputError(f"approval {ref} row does not mention {key!r}")


def _reason_ok(entry: Mapping[str, Any]) -> bool:
    return isinstance(entry.get("reason"), str) and bool(entry["reason"].strip())


def parse_rls_manifest(raw: Any, resolver_root: Path = REPO_ROOT) -> RlsManifest:
    """ADR-010 D3.3/D3.4 manifest v2; every approval must resolve."""
    keys = {"version", "platform_scope_relations", "reviewed_security_definer_functions"}
    if (not isinstance(raw, dict) or set(raw) != keys
            or type(raw["version"]) is not int or raw["version"] != 2):
        raise GateInputError(
            "RLS manifest must be exactly {version: 2, platform_scope_relations, "
            "reviewed_security_definer_functions}"
        )
    rels, funcs = raw["platform_scope_relations"], raw["reviewed_security_definer_functions"]
    if not isinstance(rels, dict) or not isinstance(funcs, dict):
        raise GateInputError("RLS manifest sections must be objects")
    platform: dict[str, str] = {}
    for name, entry in rels.items():
        if not _TABLE_RE.fullmatch(name):
            raise GateInputError(f"manifest relation {name!r} is not schema.relation")
        if (not isinstance(entry, dict) or set(entry) != {"kind", "reason", "approval"}
                or entry["kind"] not in ("table", "matview") or not _reason_ok(entry)):
            raise GateInputError(
                f"manifest relation {name!r} needs exactly kind (table|matview), "
                "a non-empty reason and an approval"
            )
        resolve_approval(entry["approval"], name, resolver_root)
        platform[name] = entry["kind"]
    for key, entry in funcs.items():
        if (not key.strip() or not isinstance(entry, dict)
                or set(entry) != {"reason", "approval"} or not _reason_ok(entry)):
            raise GateInputError(f"manifest function {key!r} needs exactly reason and approval")
        resolve_approval(entry["approval"], key, resolver_root)
    return RlsManifest(platform, frozenset(funcs))


def load_rls_manifest(path: Path = RLS_MANIFEST_PATH,
                      resolver_root: Path = REPO_ROOT) -> RlsManifest:
    """ADR-010 D3.2: the fixed committed path; missing or symlinked is ERROR."""
    if path.is_symlink() or not path.is_file():
        raise GateInputError(f"RLS manifest {path} missing or a symlink")
    return parse_rls_manifest(_load_json(path), resolver_root)


# --- catalog collection (ADR-010 D2: pinned search_path, one read-only snapshot) ---

_G_SQL = """g(oid) AS (
  SELECT r.oid FROM pg_catalog.pg_roles r
   WHERE {exists} AND pg_catalog.pg_has_role(%(rt)s::pg_catalog.oid, r.oid, 'MEMBER')
  UNION SELECT 0::pg_catalog.oid)"""
# ADR-010 A1.2: system namespaces are pg_* and information_schema, except temp ones.
_SYS_NS = ("(({ns} LIKE 'pg\\_%%' OR {ns} = 'information_schema') "
           "AND {ns} !~ '^pg_(toast_)?temp_[0-9]+$')")
_CLS = ("CASE {k} WHEN 'r' THEN 'table' WHEN 'p' THEN 'table' WHEN 'v' THEN 'view' "
        "WHEN 'm' THEN 'matview' WHEN 'f' THEN 'foreign_table' WHEN 'S' THEN 'sequence' "
        "ELSE 'relation' END")


def _acl_select(cls: str, src: str, oid: str, classoid: str, subid: str, acl: str,
                default: str, identity: str, system: str, relation: str = "NULL",
                schema: str = "NULL", where: str = "true") -> str:
    # `system` is the system-NAMESPACE test; A1.2 combines it with the stock-oid test
    # (namespace-less objects are system only through pg_init_privs).
    return f"""
SELECT {cls}, {identity}, a.privilege_type::text,
       CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(a.grantee)::text END,
       {system}, {oid} < {FIRST_NORMAL_OBJECT_ID}, ip.objoid IS NOT NULL,
       (a.grantee, a.privilege_type) IN (
         SELECT i.grantee, i.privilege_type
           FROM pg_catalog.aclexplode(coalesce(ip.initprivs, {default})) i),
       {relation}::text, {schema}::text
FROM {src}
LEFT JOIN pg_catalog.pg_init_privs ip
       ON ip.objoid = {oid} AND ip.classoid = '{classoid}'::pg_catalog.regclass
      AND ip.objsubid = {subid}
CROSS JOIN LATERAL pg_catalog.aclexplode(coalesce({acl}, {default})) a
WHERE a.grantee IN (SELECT oid FROM g) AND {where}"""


_REL_SRC = ("pg_catalog.pg_class o JOIN pg_catalog.pg_namespace n ON n.oid = o.relnamespace")
_ACL_SQL = "WITH " + _G_SQL + " " + " UNION ALL ".join([
    _acl_select("'database'", "pg_catalog.pg_database o", "o.oid", "pg_catalog.pg_database", "0",
                "o.datacl", "pg_catalog.acldefault('d', o.datdba)", "o.datname::text", "false",
                where="o.datname = pg_catalog.current_database()"),
    _acl_select("'schema'", "pg_catalog.pg_namespace o", "o.oid", "pg_catalog.pg_namespace", "0",
                "o.nspacl", "pg_catalog.acldefault('n', o.nspowner)", "o.nspname::text",
                _SYS_NS.format(ns="o.nspname"), schema="o.nspname"),
    _acl_select(_CLS.format(k="o.relkind"), _REL_SRC, "o.oid", "pg_catalog.pg_class", "0",
                "o.relacl",
                "pg_catalog.acldefault(CASE WHEN o.relkind = 'S' THEN 's' ELSE 'r' END"
                "::\"char\", o.relowner)",
                "n.nspname || '.' || o.relname", _SYS_NS.format(ns="n.nspname"),
                relation="n.nspname || '.' || o.relname", schema="n.nspname"),
    _acl_select(_CLS.format(k="o.relkind"),
                "pg_catalog.pg_attribute att JOIN " + _REL_SRC + " ON o.oid = att.attrelid",
                "o.oid", "pg_catalog.pg_class", "att.attnum", "att.attacl",
                "NULL::pg_catalog.aclitem[]",
                "n.nspname || '.' || o.relname || '.' || att.attname",
                _SYS_NS.format(ns="n.nspname"),
                relation="n.nspname || '.' || o.relname", schema="n.nspname",
                where="att.attnum > 0 AND NOT att.attisdropped AND att.attacl IS NOT NULL"),
    _acl_select("'function'", "pg_catalog.pg_proc o JOIN pg_catalog.pg_namespace n "
                "ON n.oid = o.pronamespace", "o.oid", "pg_catalog.pg_proc", "0", "o.proacl",
                "pg_catalog.acldefault('f', o.proowner)", "o.oid::pg_catalog.regprocedure::text",
                _SYS_NS.format(ns="n.nspname"), schema="n.nspname"),
    _acl_select("'type'", "pg_catalog.pg_type o JOIN pg_catalog.pg_namespace n "
                "ON n.oid = o.typnamespace", "o.oid", "pg_catalog.pg_type", "0", "o.typacl",
                "pg_catalog.acldefault('T', o.typowner)", "pg_catalog.format_type(o.oid, NULL)",
                _SYS_NS.format(ns="n.nspname"), schema="n.nspname"),
    _acl_select("'language'", "pg_catalog.pg_language o", "o.oid", "pg_catalog.pg_language", "0",
                "o.lanacl", "pg_catalog.acldefault('l', o.lanowner)", "o.lanname::text", "false"),
    _acl_select("'large_object'", "pg_catalog.pg_largeobject_metadata o", "o.oid",
                "pg_catalog.pg_largeobject", "0", "o.lomacl",
                "pg_catalog.acldefault('L', o.lomowner)", "o.oid::text", "false"),
    _acl_select("'fdw'", "pg_catalog.pg_foreign_data_wrapper o", "o.oid",
                "pg_catalog.pg_foreign_data_wrapper", "0", "o.fdwacl",
                "pg_catalog.acldefault('F', o.fdwowner)", "o.fdwname::text", "false"),
    _acl_select("'server'", "pg_catalog.pg_foreign_server o", "o.oid",
                "pg_catalog.pg_foreign_server", "0", "o.srvacl",
                "pg_catalog.acldefault('S', o.srvowner)", "o.srvname::text", "false"),
    _acl_select("'tablespace'", "pg_catalog.pg_tablespace o", "o.oid", "pg_catalog.pg_tablespace",
                "0", "o.spcacl", "pg_catalog.acldefault('t', o.spcowner)", "o.spcname::text",
                "false"),
    _acl_select("'parameter'", "pg_catalog.pg_parameter_acl o", "o.oid",
                "pg_catalog.pg_parameter_acl", "0", "o.paracl", "NULL::pg_catalog.aclitem[]",
                "o.parname::text", "false"),
])

_CLOSURE_SQL = """
SELECT r.rolname::text, r.oid::int8, r.rolsuper, r.rolbypassrls, r.rolreplication,
       r.rolcreaterole, r.rolcreatedb
  FROM pg_catalog.pg_roles r
 WHERE pg_catalog.pg_has_role(%(rt)s::pg_catalog.oid, r.oid, 'MEMBER')
 ORDER BY 1"""

_OWNED_SQL = "WITH " + _G_SQL + """
SELECT DISTINCT pg_catalog.replace(x.type, ' ', '_'), x.identity FROM (
  SELECT (pg_catalog.pg_identify_object(s.classid, s.objid, s.objsubid)).*
    FROM pg_catalog.pg_shdepend s
   WHERE s.deptype = 'o' AND s.refclassid = 'pg_catalog.pg_authid'::pg_catalog.regclass
     AND s.refobjid IN (SELECT oid FROM g WHERE oid <> 0)
     AND s.dbid IN (0, (SELECT d.oid FROM pg_catalog.pg_database d
                         WHERE d.datname = pg_catalog.current_database()))
  UNION ALL
  SELECT (pg_catalog.pg_identify_object('pg_catalog.pg_database'::pg_catalog.regclass, d.oid, 0)).*
    FROM pg_catalog.pg_database d
   WHERE d.datname = pg_catalog.current_database() AND d.datdba IN (SELECT oid FROM g)
  UNION ALL
  SELECT (pg_catalog.pg_identify_object('pg_catalog.pg_namespace'::pg_catalog.regclass, n.oid, 0)).*
    FROM pg_catalog.pg_namespace n WHERE n.nspowner IN (SELECT oid FROM g)
  UNION ALL
  SELECT (pg_catalog.pg_identify_object('pg_catalog.pg_class'::pg_catalog.regclass, c.oid, 0)).*
    FROM pg_catalog.pg_class c WHERE c.relowner IN (SELECT oid FROM g)
) x ORDER BY 1, 2"""

_RELATIONS_SQL = r"""
SELECT o.oid::int8, n.nspname::text, o.relname::text, o.relkind::text,
       o.relrowsecurity, o.relforcerowsecurity, a.attnum IS NOT NULL,
       coalesce(a.atttypid = 'pg_catalog.uuid'::pg_catalog.regtype, false),
       coalesce(a.attnotnull, false), coalesce(o.reloptions, '{}')::text[]
  FROM pg_catalog.pg_class o
  JOIN pg_catalog.pg_namespace n ON n.oid = o.relnamespace
  LEFT JOIN pg_catalog.pg_attribute a
         ON a.attrelid = o.oid AND a.attname = 'tenant_id' AND a.attnum > 0
        AND NOT a.attisdropped
 WHERE o.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
   AND n.nspname NOT LIKE 'pg\_%%' AND n.nspname <> 'information_schema'
 ORDER BY 2, 3"""

_POLICIES_SQL = "WITH " + _G_SQL + """
SELECT p.polname::text, p.polpermissive, p.polcmd::text,
       pg_catalog.pg_get_expr(p.polqual, p.polrelid),
       pg_catalog.pg_get_expr(p.polwithcheck, p.polrelid),
       EXISTS (SELECT 1 FROM pg_catalog.unnest(p.polroles) t(o) WHERE t.o IN (SELECT oid FROM g)),
       ARRAY(SELECT (pg_catalog.pg_identify_object(d.refclassid, d.refobjid, 0)).identity
               FROM pg_catalog.pg_depend d
              WHERE d.classid = 'pg_catalog.pg_policy'::pg_catalog.regclass AND d.objid = p.oid
                AND NOT (d.refclassid = 'pg_catalog.pg_class'::pg_catalog.regclass
                         AND d.refobjid = p.polrelid)
              ORDER BY 1)
  FROM pg_catalog.pg_policy p WHERE p.polrelid = %(oid)s::pg_catalog.oid ORDER BY 1"""

_SECURITY_DEFINER_SQL = "WITH " + _G_SQL + """
SELECT o.oid::pg_catalog.regprocedure::text
  FROM pg_catalog.pg_proc o JOIN pg_catalog.pg_namespace n ON n.oid = o.pronamespace
 WHERE o.prosecdef
   -- ADR-010 A1.2: the same system-object definition as the ACL scan
   AND NOT ((""" + _SYS_NS.format(ns="n.nspname") + f""" AND o.oid < {FIRST_NORMAL_OBJECT_ID})
            OR EXISTS (SELECT 1 FROM pg_catalog.pg_init_privs ip WHERE ip.objoid = o.oid
                       AND ip.classoid = 'pg_catalog.pg_proc'::pg_catalog.regclass))
   AND EXISTS (SELECT 1 FROM pg_catalog.aclexplode(
                 coalesce(o.proacl, pg_catalog.acldefault('f', o.proowner))) a
                WHERE a.grantee IN (SELECT oid FROM g) AND a.privilege_type = 'EXECUTE')
 ORDER BY 1"""

_SETTINGS_SQL = "WITH " + _G_SQL + """
SELECT CASE WHEN s.setrole = 0 THEN '*' ELSE pg_catalog.pg_get_userbyid(s.setrole)::text END,
       CASE WHEN s.setdatabase = 0 THEN '*' ELSE pg_catalog.current_database()::text END, c
  FROM pg_catalog.pg_db_role_setting s, pg_catalog.unnest(s.setconfig) c
 WHERE s.setrole IN (SELECT oid FROM g)
   AND s.setdatabase IN (0, (SELECT d.oid FROM pg_catalog.pg_database d
                              WHERE d.datname = pg_catalog.current_database()))
 ORDER BY 1, 2, 3"""


def _rows(conn: Any, query: str, params: Mapping[str, Any] | None = None) -> list[Any]:
    return list(conn.execute(query, params or {}).fetchall())


def _collect(conn: Any, runtime_role: str, schemas: Sequence[str] | None) -> RlsCatalog:
    version = int(_rows(conn, "SELECT pg_catalog.current_setting('server_version_num')")[0][0])
    database = str(_rows(conn, "SELECT pg_catalog.current_database()::text")[0][0])
    rt = _rows(conn, "SELECT oid::int8 FROM pg_catalog.pg_roles WHERE rolname = %(n)s",
               {"n": runtime_role})
    exists = bool(rt)
    params = {"rt": rt[0][0] if exists else 0}
    g_exists = "true" if exists else "false"

    def q(sql_text: str, extra: Mapping[str, Any] | None = None) -> list[Any]:
        return _rows(conn, sql_text.replace("{exists}", g_exists), {**params, **(extra or {})})

    closure = tuple(RoleInfo(r[0], int(r[1]), *map(bool, r[2:]))
                    for r in (q(_CLOSURE_SQL) if exists else []))
    grants = []
    for cls, ident, priv, grantee, sys_ns, stock, has_init, in_init, rel, sch in q(_ACL_SQL):
        system = bool((sys_ns and stock) or has_init)  # ADR-010 A1.2
        grants.append(AclGrant(cls, ident, priv, grantee, system, bool(in_init), rel, sch,
                               non_stock=bool(sys_ns) and not system,
                               has_init_privs=bool(has_init)))
    owned = tuple((str(r[0]), str(r[1])) for r in q(_OWNED_SQL))
    all_schemas = {r[0] for r in _rows(conn, "SELECT nspname::text FROM pg_catalog.pg_namespace")}
    if schemas:
        missing = tuple(s for s in schemas if s not in all_schemas)
        scanned = tuple(schemas)
    else:
        missing = ()
        scanned = tuple(sorted(s for s in all_schemas
                               if not s.startswith("pg_") and s != "information_schema"))
    relations = []
    for oid, sch, name, kind, enabled, forced, has_tid, is_uuid, notnull, opts in _rows(
            conn, _RELATIONS_SQL):
        policies: tuple[Policy, ...] = ()
        if kind in ("r", "p") and has_tid:
            policies = tuple(Policy(p[0], bool(p[1]), p[2], p[3], p[4], bool(p[5]), tuple(p[6]))
                             for p in q(_POLICIES_SQL, {"oid": oid}))
        invoker = any(o.split("=", 1)[0] == "security_invoker"
                      and o.split("=", 1)[-1].lower() in _TRUTHY for o in opts)
        relations.append(Relation(sch, name, kind, bool(has_tid), bool(is_uuid), bool(notnull),
                                  bool(enabled), bool(forced), policies, invoker))
    settings = [f"{c}@role={r},database={d}" for r, d, c in q(_SETTINGS_SQL)]
    defaults = tuple(s for s in settings if s.startswith("app."))
    lo_compat = any(s.split("=", 1)[0].lower() == "lo_compat_privileges"
                    and s.split("=", 1)[1].split("@", 1)[0].lower() in _TRUTHY for s in settings)
    session_ctx = _rows(conn, "SELECT pg_catalog.current_setting('app.tenant_id', true)")[0][0]
    if session_ctx:
        defaults += ("app.tenant_id@inspector_session",)
    lo_now = _rows(conn, "SELECT pg_catalog.current_setting('lo_compat_privileges')")[0][0]
    return RlsCatalog(
        runtime_role, exists, version, database, closure, tuple(relations), tuple(grants), owned,
        tuple(r[0] for r in q(_SECURITY_DEFINER_SQL)), defaults,
        lo_compat or str(lo_now).lower() in _TRUTHY, scanned, missing,
    )


def collect_rls_catalog(conn: Any, runtime_role: str,
                        schemas: Sequence[str] | None = None) -> RlsCatalog:
    """ADR-010 D2: pin search_path first, verify it, then read the whole catalog in
    one REPEATABLE READ READ ONLY transaction. Any failure is GateInputError (ERROR)."""
    if getattr(conn, "autocommit", None) is not True:
        raise GateInputError("inspector connection must be in autocommit mode")
    try:
        conn.execute(f"SET search_path = {PINNED_SEARCH_PATH}")
        try:
            got = _rows(conn, "SELECT pg_catalog.current_setting('search_path')")
            if not got or got[0][0] != PINNED_SEARCH_PATH:
                raise GateInputError(f"search_path read-back {got!r} != {PINNED_SEARCH_PATH!r}")
            conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            try:
                return _collect(conn, runtime_role, schemas)
            finally:
                conn.execute("ROLLBACK")
        finally:
            conn.execute("RESET search_path")
    except GateInputError:
        raise
    except Exception as exc:  # noqa: BLE001 — fail closed: any read failure is ERROR, never "empty"
        raise GateInputError(f"catalog read failed ({type(exc).__name__})") from None


# --- verdict (pure) ------------------------------------------------------------------


def _policy_gaps(rel: Relation, predicate: str) -> list[str]:
    if not rel.policies:
        return ["no RLS policy defined"]
    gaps = []
    for p in rel.policies:
        if not (p.permissive and p.applies_to_runtime):
            continue  # restrictive policies only narrow; unreachable ones never apply
        if p.command in ("*", "r", "w", "d") and p.using != predicate:
            gaps.append(f"policy {p.name!r} USING {p.using} is not the canonical tenant predicate")
        check = p.with_check if p.with_check is not None else p.using
        if p.command in ("*", "a", "w") and check != predicate:
            gaps.append(
                f"policy {p.name!r} WITH CHECK {check} is not the canonical tenant predicate"
            )
        if p.foreign_dependencies:
            gaps.append(f"policy {p.name!r} depends on {list(p.foreign_dependencies)}")
    return gaps


def _information_schema_pinned(gr: AclGrant, pin: Mapping[str, str] | None) -> bool:
    """ADR-010 A1.3: exact per-object PG16 information_schema initial PUBLIC grants."""
    if (pin is None or not gr.system or gr.has_init_privs or gr.grantee != "PUBLIC"
            or gr.schema != "information_schema"):
        return False
    if gr.obj_class == "schema":
        return gr.identity == "information_schema" and gr.privilege == "USAGE"
    return (gr.privilege == "SELECT" and gr.relation is not None and gr.identity == gr.relation
            and pin.get(gr.relation.split(".", 1)[1]) == gr.obj_class)


def evaluate_rls(catalog: RlsCatalog, manifest: RlsManifest = EMPTY_RLS_MANIFEST,
                 required_tables: Iterable[str] = ()) -> GateReport:
    """Pure ADR-010 verdict over a collected catalog — no database access."""
    def err(detail: str, subject: str = "-") -> GateReport:
        return GateReport("rls", ERROR, [Violation("RLS_GATE_INPUT_INVALID", subject, detail)])

    if catalog.missing_schemas:
        return err("requested schema(s) do not exist; a typo must not shrink the scan",
                   ",".join(catalog.missing_schemas))
    predicate = PINNED_TENANT_PREDICATES.get(catalog.server_version_num // 10000)
    if predicate is None:
        return err(f"server_version_num {catalog.server_version_num}: no pinned tenant predicate")

    rt = catalog.runtime
    v: list[Violation] = []

    def elevated(identity: str, token: str) -> None:
        v.append(Violation("RLS_RUNTIME_ROLE_ELEVATED", f"{rt}/{identity}", token))

    if not catalog.runtime_exists:
        v.append(Violation("RLS_RUNTIME_ROLE_MISSING", rt, "runtime role not found"))
    for role in catalog.closure:  # D1.1, D1.2
        for attr, on in (("SUPERUSER", role.superuser), ("BYPASSRLS", role.bypassrls),
                         ("REPLICATION", role.replication), ("CREATEROLE", role.createrole),
                         ("CREATEDB", role.createdb)):
            if on:
                elevated(role.name, f"ATTRIBUTE:{attr}@{role.name}")
        if role.oid < FIRST_NORMAL_OBJECT_ID or role.name.startswith("pg_"):
            elevated(role.name, f"PREDEFINED_ROLE:{role.name}")
    for cls, identity in catalog.owned:  # D1.3
        elevated(identity, f"OWNS:{cls}:{identity}")
    for source in catalog.tenant_context_defaults:  # D1.7
        elevated(source, f"TENANT_CONTEXT_DEFAULT:{source}")
    if catalog.lo_compat_privileges:
        elevated(catalog.database, f"ATTRIBUTE:LO_COMPAT_PRIVILEGES@{catalog.database}")

    rels = {r.qualified: r for r in catalog.relations}
    scanned = set(catalog.scanned_schemas)
    granted: set[str] = set()
    info_pin = PINNED_INFORMATION_SCHEMA_SELECT.get(catalog.server_version_num // 10000)
    for gr in catalog.grants:  # D1.4, D1.5, D1.5a, D1.6
        if gr.non_stock:  # A1.2: application object in a system schema
            elevated(gr.identity, f"NON_STOCK_SYSTEM_OBJECT:{gr.obj_class}:{gr.identity}:"
                                  f"{gr.privilege}@{gr.grantee}")
            continue
        if gr.system:
            if not gr.in_initial and not _information_schema_pinned(gr, info_pin):
                elevated(gr.identity, f"SYSTEM_ACL_MODIFIED:{gr.identity}:"
                                      f"{gr.privilege}@{gr.grantee}")
            continue
        allowed = ALLOWED_PRIVILEGES.get(gr.obj_class, frozenset())
        if gr.privilege not in allowed or (gr.grantee == "PUBLIC" and gr.obj_class in _NO_PUBLIC):
            elevated(gr.identity, f"PRIVILEGE:{gr.obj_class}:{gr.identity}:"
                                  f"{gr.privilege}@{gr.grantee}")
        if gr.relation:
            granted.add(gr.relation)
    for name in sorted(granted):
        if name.split(".", 1)[0] not in scanned:
            elevated(name, f"OUT_OF_SCOPE:{name}")
    for key in catalog.security_definer:
        if key not in manifest.reviewed_security_definer_functions:
            v.append(Violation("RLS_SECURITY_DEFINER_UNREVIEWED", f"{rt}/{key}",
                               "SECURITY DEFINER function executable by the runtime closure "
                               "is not in the reviewed manifest section"))

    for name, kind in sorted(manifest.platform_scope_relations.items()):  # D3.5
        rel = rels.get(name)
        if rel is None:
            v.append(Violation("RLS_EXEMPTION_INVALID", name, "manifest relation does not exist"))
        elif rel.has_tenant_id:
            v.append(Violation("RLS_EXEMPTION_INVALID", name, "relation has tenant_id"))
        elif {"table": ("r", "p"), "matview": ("m",)}[kind].count(rel.kind) == 0:
            v.append(Violation("RLS_EXEMPTION_INVALID", name,
                               f"manifest kind {kind!r} does not match relkind {rel.kind!r}"))

    checked: list[str] = []
    for rel in catalog.relations:  # D4.1, D4.4
        q = rel.qualified
        if rel.schema not in scanned:
            continue
        if rel.kind in ("r", "p"):
            if not rel.has_tenant_id:
                if manifest.platform_scope_relations.get(q) != "table":
                    v.append(Violation("RLS_TABLE_UNCLASSIFIED", q,
                                       "no tenant_id column and not a manifest platform table"))
                continue
            checked.append(q)
            if not rel.tenant_id_uuid:
                v.append(Violation("RLS_TENANT_ID_NOT_UUID", f"{q}.tenant_id",
                                   "tenant_id is not uuid"))
            if not rel.tenant_id_not_null:
                v.append(Violation("RLS_TENANT_ID_NULLABLE", f"{q}.tenant_id",
                                   "tenant_id is nullable"))
            if not rel.rls_enabled:
                v.append(Violation("RLS_NOT_ENFORCED", q, "ENABLE ROW LEVEL SECURITY missing"))
            if not rel.rls_forced:
                v.append(Violation("RLS_NOT_ENFORCED", q, "FORCE ROW LEVEL SECURITY missing"))
            v += [Violation("RLS_NOT_ENFORCED", q, g) for g in _policy_gaps(rel, predicate)]
        elif q in granted:
            if rel.kind == "v" and not rel.security_invoker:
                v.append(Violation("RLS_NOT_ENFORCED", q,
                                   "view granted to the runtime closure lacks security_invoker"))
            elif rel.kind == "m" and (rel.has_tenant_id
                                      or manifest.platform_scope_relations.get(q) != "matview"):
                v.append(Violation("RLS_NOT_ENFORCED", q,
                                   "materialized view granted to the runtime closure is not a "
                                   "manifest platform matview without tenant_id"))
            elif rel.kind == "f":
                v.append(Violation("RLS_NOT_ENFORCED", q,
                                   "foreign table granted to the runtime closure"))

    present = {r.qualified: r for r in catalog.relations if r.kind in ("r", "p")}
    for name in sorted(set(required_tables)):
        if name not in present or not present[name].has_tenant_id:
            v.append(Violation("RLS_REQUIRED_TABLE_MISSING", name,
                               "required tenant table not found"))
    vacuous = None if checked else "no tenant table in scope; an empty scan proves nothing"
    return _finish("rls", v, checked, vacuous, [f"runtime role: {rt}"])


def run_rls_gate(conn: Any, runtime_role: str, schemas: Sequence[str] | None = None,
                 required_tables: Iterable[str] = (), manifest: Any = None,
                 resolver_root: Path = REPO_ROOT) -> GateReport:
    """`manifest=None` reads the fixed committed path (the only CLI behaviour);
    tests may inject a parsed or raw manifest through this API only (D3.2)."""
    try:
        if manifest is None:
            parsed = load_rls_manifest(resolver_root=resolver_root)
        elif isinstance(manifest, RlsManifest):
            parsed = manifest
        else:
            parsed = parse_rls_manifest(manifest, resolver_root)
        catalog = collect_rls_catalog(conn, runtime_role, schemas)
    except GateInputError as exc:
        return GateReport("rls", ERROR, [Violation("RLS_GATE_INPUT_INVALID", "-", str(exc))])
    return evaluate_rls(catalog, parsed, required_tables)


# --- permission gate (ADR-009) ---------------------------------------------------

SCOPES = frozenset({
    "tenant", "organization", "brand", "region", "location", "department",
    "assigned_clients", "self", "explicit_resource",
})  # TSD §8.4 scope grammar
# ADR-009 D4 closed enum; only `authenticated` needs no written justification.
AUTH_CLASSES = ("authenticated", "credential_exchange", "provider_signature", "anonymous")
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
DECLARATION_KEY = "x-veyro-permission"
AUTH_KEY = "x-veyro-authentication"
DECLARATION_FIELDS = ("action", "resource", "scope")
_SEGMENT = r"[a-z][a-z0-9_]*"
_ACTION_RE = re.compile(_SEGMENT)
_RESOURCE_RE = re.compile(rf"{_SEGMENT}\.{_SEGMENT}")
_PERMISSION_RE = re.compile(rf"{_SEGMENT}\.{_SEGMENT}\.{_SEGMENT}")
# ADR-009 D1.2: 3.1.x only (3.0 not emitted by the reference stack; 3.2 adds
# `query`/`additionalOperations`).
_OPENAPI_VERSION_RE = re.compile(r"3\.1\.[0-9]+")
_PATH_ITEM_KEYS = frozenset(HTTP_METHODS) | {"summary", "description", "servers", "parameters"}
_PATH_PARAM_RE = re.compile(r"\{[^}]*\}")
_IGNORED_FILES = {".gitkeep"}

DEFAULT_OPENAPI_DIR = REPO_ROOT / "contracts" / "openapi"
DEFAULT_REGISTRY = REPO_ROOT / "contracts" / "permissions" / "registry.json"


@dataclass(frozen=True)
class RegistryEntry:
    scopes: frozenset[str]
    authentication: str
    approval: str | None = None  # ADR-010 D5.1: required unless `authenticated`


@dataclass(frozen=True)
class Operation:
    endpoint: str
    method: str
    path_key: str  # path template with parameter names erased: /a/{id} == /a/{x}
    operation_id: str | None
    authentication: str | None  # valid declared class, else None
    permission: str | None
    approval: str | None = None


def parse_registry(raw: Any, resolver_root: Path = REPO_ROOT) -> dict[str, RegistryEntry]:
    """ADR-009 D2 as amended by ADR-010 D5.1 (version 2; non-`authenticated`
    entries carry a resolving ADR/OWN `approval` that names the permission)."""
    if (not isinstance(raw, dict) or set(raw) != {"version", "permissions"}
            or type(raw["version"]) is not int or raw["version"] != 2):
        raise GateInputError('registry must be exactly {"version": 2, "permissions": {...}}')
    perms = raw["permissions"]
    if not isinstance(perms, dict):
        raise GateInputError("registry 'permissions' must be an object")
    out: dict[str, RegistryEntry] = {}
    for name, entry in perms.items():
        if not _PERMISSION_RE.fullmatch(name):
            raise GateInputError(f"registry permission {name!r} is not <domain>.<resource>.<action>")
        if not isinstance(entry, dict):
            raise GateInputError(f"registry permission {name!r} must be an object")
        auth = entry.get("authentication")
        if not (isinstance(auth, str) and auth in AUTH_CLASSES):
            raise GateInputError(
                f"registry permission {name!r} authentication {auth!r} not in {list(AUTH_CLASSES)}"
            )
        keys = {"scopes", "authentication"}
        if auth != "authenticated":
            keys |= {"justification", "approval"}
            just = entry.get("justification")
            if not (isinstance(just, str) and just.strip()):
                raise GateInputError(
                    f"registry permission {name!r} ({auth}) needs a non-empty justification"
                )
        if set(entry) != keys:
            raise GateInputError(
                f"registry permission {name!r} keys must be exactly {sorted(keys)}"
            )
        scopes = entry["scopes"]
        if (not isinstance(scopes, list) or not scopes
                or not all(isinstance(s, str) and s in SCOPES for s in scopes)
                or len(set(scopes)) != len(scopes)):
            raise GateInputError(
                f"registry permission {name!r} scopes must be a non-empty, duplicate-free "
                f"subset of the TSD §8.4 scope grammar"
            )
        approval = entry.get("approval")
        if auth != "authenticated":
            resolve_approval(approval, name, resolver_root)
        out[name] = RegistryEntry(frozenset(scopes), auth, approval)
    return out


def _permission_problem(decl: Any, registry: Mapping[str, RegistryEntry]) -> str | None:
    if decl is None:
        return f"no {DECLARATION_KEY} declaration"
    if not isinstance(decl, dict):
        return f"{DECLARATION_KEY} must be an object"
    missing = [f for f in DECLARATION_FIELDS if f not in decl]
    if missing:
        return f"declaration missing {', '.join(missing)}"
    extra = sorted(set(decl) - set(DECLARATION_FIELDS))
    if extra:
        return f"declaration has undeclared key(s) {', '.join(extra)}"
    action, resource, scope = (decl[f] for f in DECLARATION_FIELDS)
    if not (isinstance(action, str) and _ACTION_RE.fullmatch(action)):
        return f"action {action!r} is not a lowercase identifier"
    if not (isinstance(resource, str) and _RESOURCE_RE.fullmatch(resource)):
        return f"resource {resource!r} is not <domain>.<resource>"
    if not (isinstance(scope, str) and scope in SCOPES):
        return f"scope {scope!r} is not in the TSD §8.4 scope grammar"
    name = f"{resource}.{action}"
    if name not in registry:
        return f"permission {name!r} is not registered"
    if scope not in registry[name].scopes:
        return f"scope {scope!r} is not registered for {name!r}"
    return None


def _scheme_names(security: Any, where: str, schemes: set[str]) -> list[set[str]]:
    """ADR-010 D5.2: a security value is a JSON array of {scheme: [string, ...]} objects
    naming only defined schemes; anything else (including null) is ERROR."""
    if not isinstance(security, list) or not all(
        isinstance(req, dict) and all(
            isinstance(v, list) and all(isinstance(x, str) for x in v) for v in req.values())
        for req in security
    ):
        raise GateInputError(f"{where}: security must be a list of {{scheme: [strings]}} objects")
    reqs = [set(req) for req in security]
    undefined = sorted(set().union(*reqs) - schemes) if reqs else []
    if undefined:
        raise GateInputError(f"{where}: security names undefined scheme(s) {undefined}")
    return reqs


_SCHEME_REQUIRED = {"apiKey": ("name", "in"), "http": ("scheme",), "mutualTLS": (),
                    "oauth2": ("flows",), "openIdConnect": ("openIdConnectUrl",)}


def _validate_security_schemes(raw: Any, source: str) -> set[str]:
    """ADR-010 D5.2: every defined scheme is a well-formed Security Scheme Object."""
    if not isinstance(raw, dict):
        raise GateInputError(f"{source}: components.securitySchemes must be an object")
    for name, scheme in raw.items():
        where = f"{source}: securitySchemes.{name}"
        if not isinstance(scheme, dict) or "$ref" in scheme:
            raise GateInputError(f"{where} must be an inline Security Scheme Object")
        kind = scheme.get("type")
        if kind not in _SCHEME_REQUIRED:
            raise GateInputError(f"{where} type {kind!r} unsupported")
        for req in _SCHEME_REQUIRED[kind]:
            value = scheme.get(req)
            if req == "flows":
                ok = isinstance(value, dict) and bool(value)
            else:
                ok = isinstance(value, str) and bool(value.strip())
            if not ok:
                raise GateInputError(f"{where} ({kind}) needs a non-empty {req!r}")
        if kind == "apiKey" and scheme["in"] not in ("query", "header", "cookie"):
            raise GateInputError(f"{where} apiKey 'in' must be query/header/cookie")
    return set(raw)


def _security_problem(auth: str, op: Mapping[str, Any], root: Any, schemes: set[str],
                      where: str) -> str | None:
    """ADR-009 D4.3: the declared class must agree with native OpenAPI `security`."""
    explicit = "security" in op
    effective = op["security"] if explicit else root
    # An explicit `security` key is always validated, so `null` is ERROR, never "absent".
    reqs = (_scheme_names(effective, where, schemes)
            if explicit or effective is not None else None)
    if auth == "authenticated":
        if not reqs:
            return "authenticated operation has no effective security requirement"
        if any(not r for r in reqs):
            return "authenticated operation allows the empty security requirement {}"
    elif auth == "anonymous":
        if not (explicit and op["security"] == []):
            return 'anonymous operation must set "security": [] explicitly'
    elif not explicit:  # ADR-010 D5.2: missing explicit security is ERROR, not a violation
        raise GateInputError(
            f"{where}: {auth} operation must set security explicitly, not inherit root security"
        )
    return None


def _check_operation(op: dict[str, Any], endpoint: str, root_security: Any, schemes: set[str],
                     registry: Mapping[str, RegistryEntry]) -> tuple[list[str], str | None, str | None]:
    """Return (problems, valid authentication class or None, permission name or None)."""
    problems = []
    decl = op.get(DECLARATION_KEY)
    perm_problem = _permission_problem(decl, registry)
    permission = None
    if perm_problem:
        problems.append(perm_problem)
    elif isinstance(decl, dict):
        permission = f"{decl['resource']}.{decl['action']}"
    auth = op.get(AUTH_KEY)
    if auth is None:
        problems.append(f"no {AUTH_KEY} declaration")
        return problems, None, permission
    if not (isinstance(auth, str) and auth in AUTH_CLASSES):
        problems.append(f"{AUTH_KEY} {auth!r} is not one of {list(AUTH_CLASSES)}")
        return problems, None, permission
    if permission and registry[permission].authentication != auth:
        problems.append(
            f"{AUTH_KEY} {auth!r} does not match registry class "
            f"{registry[permission].authentication!r} for {permission!r}"
        )
    sec_problem = _security_problem(auth, op, root_security, schemes, endpoint)
    if sec_problem:
        problems.append(sec_problem)
    return problems, auth, permission


def check_openapi_document(doc: Any, source: str, registry: Mapping[str, RegistryEntry]
                           ) -> tuple[list[Violation], list[Operation]]:
    """ADR-009 D1/D3/D4 for one document: violations plus every scanned operation."""
    version = doc.get("openapi") if isinstance(doc, dict) else None
    if not (isinstance(version, str) and _OPENAPI_VERSION_RE.fullmatch(version)):
        raise GateInputError(f"{source}: openapi {version!r} unsupported; only 3.1.x (ADR-009)")
    assert isinstance(doc, dict)
    if "webhooks" in doc:
        raise GateInputError(f"{source}: top-level 'webhooks' is unsupported (ADR-009 D1.3)")
    components = doc.get("components", {})
    if not isinstance(components, dict):
        raise GateInputError(f"{source}: 'components' must be an object")
    for key in ("pathItems", "callbacks"):
        if key in components:
            raise GateInputError(f"{source}: components.{key} is unsupported (ADR-009 D1.3)")
    schemes = _validate_security_schemes(components.get("securitySchemes", {}), source)
    root_security = doc.get("security")
    if "security" in doc:  # null or malformed root security is ERROR (ADR-010 D5.2)
        _scheme_names(root_security, f"{source}: root", schemes)
    paths = doc.get("paths")
    if not isinstance(paths, dict):
        raise GateInputError(f"{source}: 'paths' must be an object")
    violations: list[Violation] = []
    ops: list[Operation] = []
    for path, item in paths.items():
        if not path.startswith("/"):
            raise GateInputError(f"{source}: path {path!r} must start with '/'")
        if not isinstance(item, dict):
            raise GateInputError(f"{source}: path item {path!r} must be an object")
        if "$ref" in item:
            raise GateInputError(f"{source}: $ref path item {path!r} is unsupported; inline it")
        unknown = sorted(k for k in item if k not in _PATH_ITEM_KEYS and not k.startswith("x-"))
        if unknown:
            raise GateInputError(
                f"{source}: path item {path!r} has unsupported key(s) {unknown}; "
                "an unscanned key could hide an operation"
            )
        for method in HTTP_METHODS:
            if method not in item:
                continue
            op = item[method]
            if not isinstance(op, dict):
                raise GateInputError(f"{source}: {method.upper()} {path} must be an object")
            if "callbacks" in op:
                raise GateInputError(
                    f"{source}: {method.upper()} {path} callbacks are unsupported (ADR-009 D1.3)"
                )
            op_id = op.get("operationId")
            if op_id is not None and not isinstance(op_id, str):
                raise GateInputError(f"{source}: {method.upper()} {path} operationId not a string")
            endpoint = f"{source}:{method.upper()} {path}" + (f" ({op_id})" if op_id else "")
            problems, auth, permission = _check_operation(
                op, endpoint, root_security, schemes, registry
            )
            violations += [Violation("UNREGISTERED_PERMISSION", endpoint, p) for p in problems]
            ops.append(Operation(endpoint, method, _PATH_PARAM_RE.sub("{}", path), op_id,
                                 auth, permission,
                                 registry[permission].approval if permission else None))
    return violations, ops


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [k for k, _ in pairs]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        raise ValueError(f"duplicate key(s) {dupes}")
    return dict(pairs)


def _load_json(path: Path) -> Any:
    """Strict JSON: duplicate keys (silently last-wins in json.loads) and
    nesting deep enough to exhaust the parser are input errors."""
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise GateInputError(f"{path}: unreadable JSON ({type(exc).__name__}: {exc})") from None


# GOV-01-R04 gate 3: static literal event references and registry changes.
# This deliberately covers the canonical emit_event("id") call, not dynamic event
# construction. Dynamic calls cannot establish a registered contract and fail closed.
DEFAULT_EVENT_SOURCE_DIR = REPO_ROOT / "backend" / "app"
DEFAULT_EVENT_REGISTRY = REPO_ROOT / "contracts" / "events" / "registry.json"
DEFAULT_EVENT_BASELINE = REPO_ROOT / "contracts" / "events" / "baseline.json"


def _event_entries(path: Path) -> dict[str, dict[str, Any]]:
    data = _load_json(path)
    if not isinstance(data, dict) or set(data) != {"events"} or not isinstance(data["events"], dict):
        raise GateInputError(f"{path}: expected an events object")
    entries = data["events"]
    for event_id, entry in entries.items():
        if not isinstance(event_id, str) or not event_id or not isinstance(entry, dict):
            raise GateInputError(f"{path}: invalid event entry {event_id!r}")
        if not isinstance(entry.get("schema"), dict) or not entry["schema"]:
            raise GateInputError(f"{path}: {event_id}: missing JSON Schema object")
        if not isinstance(entry.get("classification"), str) or not entry["classification"]:
            raise GateInputError(f"{path}: {event_id}: missing classification")
        if set(entry) - {"schema", "classification", "ownerApproval"}:
            raise GateInputError(f"{path}: {event_id}: unsupported fields")
    return entries


def _event_sources(directory: Path) -> list[Path]:
    """Enumerate without pathlib's silent unreadable-subtree pruning."""
    files: list[Path] = []
    def visit(root: Path) -> None:
        try:
            with os.scandir(root) as scan:
                entries = sorted(scan, key=lambda item: item.name)
            for entry in entries:
                if entry.is_symlink():
                    raise GateInputError(f"{entry.path}: symlinked event source refused")
                if entry.is_dir(follow_symlinks=False):
                    visit(Path(entry.path))
                elif entry.name.endswith(".py") and entry.is_file(follow_symlinks=False):
                    files.append(Path(entry.path))
        except OSError as exc:
            raise GateInputError(f"{root}: cannot enumerate event sources ({type(exc).__name__}: {exc})") from None
    visit(directory)
    return files


def run_event_contract_gate(source_dir: Path = DEFAULT_EVENT_SOURCE_DIR,
                            registry_path: Path = DEFAULT_EVENT_REGISTRY,
                            baseline_path: Path = DEFAULT_EVENT_BASELINE,
                            approval_root: Path = REPO_ROOT) -> GateReport:
    gate = "event-contract"
    try:
        registry = _event_entries(registry_path)
        baseline = _event_entries(baseline_path)
        if source_dir.is_symlink() or not source_dir.is_dir():
            raise GateInputError(f"{source_dir}: missing or symlinked event source directory")
        sources = _event_sources(source_dir)
        violations: list[Violation] = []
        checked: list[str] = []
        for path in sources:
            try:
                tree = ast.parse(_read_gate_text(path, str(path), "event source"), filename=str(path))
            except (SyntaxError, RecursionError) as exc:
                raise GateInputError(f"{path}: unparseable event source ({type(exc).__name__}: {exc})") from None
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not (
                    isinstance(node.func, ast.Name) and node.func.id == "emit_event"
                    or isinstance(node.func, ast.Attribute) and node.func.attr == "emit_event"
                ):
                    continue
                subject = f"{path}:{node.lineno}"
                checked.append(subject)
                if len(node.args) != 1 or node.keywords or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    violations.append(Violation("UNREGISTERED_EVENT_CONTRACT", subject, "non-literal event id"))
                elif node.args[0].value not in registry:
                    violations.append(Violation("UNREGISTERED_EVENT_CONTRACT", subject, node.args[0].value))
        for event_id, entry in registry.items():
            old = baseline.get(event_id)
            if old is not None and any(entry[field] != old[field] for field in ("schema", "classification")):
                diff = ", ".join(field for field in ("schema", "classification")
                                 if entry[field] != old[field])
                ref = entry.get("ownerApproval")
                try:
                    # Only an OWN record is sufficient for this owner decision.
                    if not isinstance(ref, str) or not re.fullmatch(r"OWN-[0-9]{3}", ref):
                        raise GateInputError("missing OWN-NNN approval")
                    resolve_approval(ref, event_id, approval_root)
                except GateInputError as exc:
                    violations.append(Violation("EVENT_CHANGE_UNAPPROVED", event_id,
                                                f"{diff} changed; {exc}"))
        return _finish(gate, violations, checked,
                       None if checked else "no emit_event references inspected", [])
    except GateInputError as exc:
        return GateReport(gate, ERROR, [Violation("EVENT_CONTRACT_GATE_INPUT_INVALID", "-", str(exc))])


def _contract_files(openapi_dir: Path) -> list[Path]:
    if openapi_dir.is_symlink() or not openapi_dir.is_dir():
        raise GateInputError(f"OpenAPI directory {openapi_dir} not found or is a symlink")
    files = []
    for entry in sorted(openapi_dir.rglob("*")):
        if entry.is_symlink():
            raise GateInputError(f"{entry}: symlinks are refused (ADR-009 D1.1)")
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise GateInputError(f"{entry}: not a regular file")
        if entry.name in _IGNORED_FILES:
            continue
        if entry.suffix != ".json":
            raise GateInputError(f"{entry}: only .json OpenAPI documents are supported")
        files.append(entry)
    return files


def _cross_document_duplicates(ops: list[Operation]) -> None:
    """ADR-009 D1.5: one owner per (method, path template) and per operationId."""
    seen_route: dict[tuple[str, str], str] = {}
    seen_id: dict[str, str] = {}
    for op in ops:
        route = (op.method, op.path_key)
        if route in seen_route:
            raise GateInputError(
                f"duplicate operation {op.method.upper()} {op.path_key}: "
                f"{seen_route[route]} and {op.endpoint}"
            )
        seen_route[route] = op.endpoint
        if op.operation_id is not None:
            if op.operation_id in seen_id:
                raise GateInputError(
                    f"duplicate operationId {op.operation_id!r}: "
                    f"{seen_id[op.operation_id]} and {op.endpoint}"
                )
            seen_id[op.operation_id] = op.endpoint


def run_permission_gate(openapi_dir: Path, registry_path: Path,
                        resolver_root: Path = REPO_ROOT) -> GateReport:
    try:
        if registry_path.is_symlink() or not registry_path.is_file():
            raise GateInputError(f"permission registry {registry_path} not found or is a symlink")
        registry = parse_registry(_load_json(registry_path), resolver_root)
        violations: list[Violation] = []
        ops: list[Operation] = []
        for f in _contract_files(openapi_dir):
            v, o = check_openapi_document(_load_json(f), f.relative_to(openapi_dir).as_posix(),
                                          registry)
            violations += v
            ops += o
        _cross_document_duplicates(ops)
    except GateInputError as exc:
        return GateReport("permission", ERROR,
                          [Violation("PERMISSION_GATE_INPUT_INVALID", "-", str(exc))])
    # ADR-009 D4.4: every non-`authenticated` operation is listed on every run.
    inventory = [
        {"endpoint": o.endpoint, "authentication": o.authentication or "",
         "permission": o.permission or "", "approval": o.approval or ""}
        for o in ops if o.authentication not in (None, "authenticated")
    ]
    counts = {c: sum(o.authentication == c for o in ops) for c in AUTH_CLASSES}
    notes = [f"{len(registry)} registered permission(s)",
             "authentication classes: " + ", ".join(f"{c}={n}" for c, n in counts.items())]
    vacuous = None if ops else "no API operation found; an empty contract proves nothing"
    report = _finish("permission", violations, [o.endpoint for o in ops], vacuous, notes)
    report.inventory = sorted(inventory, key=lambda r: r["endpoint"])
    return report


# --- module-deps gate (TSD §24.1 / §6.3; input contract fixed by ADR-011) ----------

# TSD §6.3 is the normative directed graph (`TSD_MIRROR.md` lines 1521-1570): for each
# pair, exactly one direction may import/call the opposite application interface; the
# reverse edge must remain event-driven. Pinned here, never manifest-configurable.
BIDIRECTIONAL_PAIRS: dict[frozenset[str], tuple[str, str]] = {
    frozenset({"COM-01", "COM-03"}): ("COM-01", "COM-03"),
    frozenset({"DAT-01", "REL-01"}): ("REL-01", "DAT-01"),
    frozenset({"GRO-01", "ENG-01"}): ("GRO-01", "ENG-01"),
    frozenset({"LIF-01", "GOV-04"}): ("LIF-01", "GOV-04"),
}
SHARED_PACKAGE = "_shared"  # domain-free, per .claude/rules/backend/architecture.md control 3
ROOT_IMPORTER = "_root"  # ADR-011 D4: reserved, domain-free; modules-root files are
# scanned under this importer as of GATE2-R1-D4-ROOT-FILE-SCAN-2026-10-05
# ADR-011 D4: both reserved importer names are domain-free and may never be declared
# as a manifest module name (closes b5 — `_root` fully matches `_MODULE_NAME_IDENT_RE`).
_RESERVED_MODULE_NAMES = frozenset({SHARED_PACKAGE, ROOT_IMPORTER})

DEFAULT_MODULES_DIR = REPO_ROOT / "backend" / "app" / "modules"
DEFAULT_MODULE_MANIFEST = REPO_ROOT / "contracts" / "modules" / "ownership.json"

_MODULE_NAME_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_DOMAIN_CODE_RE = re.compile(r"^[A-Z]{3}-[0-9]{2}$")
_INTERFACE_PATH_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+$")
# ADR-011 D2: "at least two characters before a mandatory trailing underscore" — `+`,
# not `*`, is load-bearing: `^[a-z][a-z0-9_]*_$` accepts `a_` (confirmed by execution
# during adjudication); this floor rejects `a`, `ab`, and `a_` and accepts `ab_`.
_PREFIX_FLOOR_RE = re.compile(r"^[a-z][a-z0-9_]+_$")
# ADR-011 D3.4/D9: these four exact values are refused as owned_table_prefixes or
# owned_schemas entries — `pg_` satisfies `_PREFIX_FLOOR_RE` (confirmed by execution),
# so without this a module could declare it and make `pg_foo` ambiguous between
# state 1 (owned) and state 4 (system).
_RESERVED_MANIFEST_VALUES = frozenset({"pg_", "pg_catalog", "pg_temp", "information_schema"})
# ADR-011 D3.4: reserved system identifiers, checked before ownership resolution.
_RESERVED_SCHEMA_NAMES = frozenset({"pg_catalog", "pg_temp", "information_schema"})
_EXTERNAL_REF_RE = re.compile(
    r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$"
)  # ADR-011 D3.5: a concrete 1- or 2-part identifier, never a wildcard
_MODULE_ENTRY_REQUIRED = ("domain", "owned_table_prefixes", "public_interfaces")
_MODULE_ENTRY_OPTIONAL = ("owned_schemas", "external_table_references")
_MODULE_ENTRY_KEYS = frozenset(_MODULE_ENTRY_REQUIRED) | frozenset(_MODULE_ENTRY_OPTIONAL)
_TOP_LEVEL_REQUIRED = frozenset({"version", "modules"})
_TOP_LEVEL_OPTIONAL = frozenset({"default_schema"})
_TOP_LEVEL_ALLOWED = _TOP_LEVEL_REQUIRED | _TOP_LEVEL_OPTIONAL

# ADR-011 D6.1: a *trigger over-approximation*, not a detector allow-list — widening
# it can only ever yield strictly more ERRORs, never a silent PASS (ends the regex
# treadmill R1-F02 named).
_TRIGGER_VERBS = frozenset({
    "SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "MERGE", "COPY", "WITH",
    "CREATE", "ALTER", "DROP", "GRANT", "REVOKE", "LOCK", "CALL", "EXECUTE",
    "REFRESH", "REINDEX", "VACUUM", "ANALYZE", "COMMENT",
})
# ADR-011 D6.3: table-position keywords shared by the backstop and extraction. "ON" is
# deliberately excluded here — it is only a table position inside GRANT/REVOKE (where
# it is handled separately below), never generically (a JOIN ... ON condition is not
# a table position). "USING" IS included (ADR-011 D6.7.4 — the vocabulary floor, not
# the fail-closed mechanism) even though a `JOIN ... USING (col)` column list is not a
# table position: the backstop below only consults this set when `idents` is already
# empty, and a JOIN's own FROM/JOIN keywords always extract at least one identifier in
# that case, so this inclusion widens the backstop's trigger without ever reclassifying
# `JOIN ... USING (id)` itself (see the P4 non-vacuity control).
_TABLE_POSITION_KEYWORDS = frozenset({"FROM", "JOIN", "INTO", "UPDATE", "TABLE", "ONLY",
                                      "REFERENCES", "USING"})
# ADR-011 D6.3: bare-table verb forms — the table name follows the verb directly,
# with no positional keyword, unless "TABLE" is explicitly present (`TRUNCATE TABLE x`),
# in which case the generic TABLE-keyword scan already covers it.
_BARE_VERB_FORMS = frozenset({"TRUNCATE", "COPY"})
_INERT_SUFFIXES = frozenset({".md", ".txt"})
_INERT_NAMES = frozenset({".gitkeep"})

# ADR-011 D3.2: the six terminal attribution states for an identifier in table position.
ATTR_OWNED = "owned"                  # states 1/2 — owner known (own vs. other decided by caller)
ATTR_CTE = "cte"                      # state 3 — bound locally (WITH ... AS, depth 0)
ATTR_SYSTEM = "system"                # state 4 — reserved system identifier
ATTR_EXTERNAL = "external"            # state 5 — declared external_table_references entry
ATTR_UNATTRIBUTED = "unattributed"    # state 6 — anything else: ERROR, never a note


@dataclass(frozen=True)
class ModuleEntry:
    name: str
    domain: str
    owned_table_prefixes: tuple[str, ...]
    owned_schemas: tuple[str, ...]
    public_interfaces: tuple[str, ...]
    external_table_references: tuple[str, ...] = ()


def _manifest_str_list(entry: Mapping[str, Any], key: str, module: str) -> list[str]:
    value = entry.get(key, [])
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise GateInputError(f"module {module!r} {key} must be a list of strings")
    return value


def _manifest_path_kind(path: Path, context: str) -> str:
    """Fail-closed classification of one path component for ADR-011 D2's
    interface-existence rule (R1-F13). Returns `"missing"`, `"symlink"`, `"dir"`,
    `"file"`, or `"other"`.

    `os.lstat` rather than `Path.exists()`/`is_file()`/`is_dir()` deliberately:
    those three return `False` on `EACCES`, which is the exact fail-open shape
    D5.4 prohibits. Here a permission error on the candidate path would otherwise
    be indistinguishable from "the file is absent" in one direction and from
    "the module directory is absent" in the other -- and in the latter the
    absence branch *skips* validation (D5.6), so swallowing `EACCES` would widen
    the approved surface. Only `ENOENT` is a real absence; every other `OSError`
    is a structured ERROR."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return "missing"
    except NotADirectoryError:
        # An intermediate component is a regular file (`a/b.py/c`): the path
        # cannot exist, and that is an absence, not an uninspectable input.
        return "missing"
    except OSError as exc:
        raise GateInputError(
            f"{context}: cannot stat {path} ({exc.strerror or exc})"
        ) from exc
    if stat.S_ISLNK(st.st_mode):
        return "symlink"
    if stat.S_ISDIR(st.st_mode):
        return "dir"
    if stat.S_ISREG(st.st_mode):
        return "file"
    return "other"


def _resolve_interface_target(module_dir: Path, parts: Sequence[str], context: str) -> Path | None:
    """ADR-011 D2/R1-F13: resolve one `public_interfaces` remainder (the dotted
    path below `<modules_root>.<module>.`) to the file it names inside the
    module's own directory -- `<parts>.py` or `<parts>/__init__.py` -- or `None`
    if it names nothing that exists.

    The walk is component-by-component with `os.lstat` so that a symlink
    *anywhere* on the path is refused rather than silently followed: `os.lstat`
    alone only declines to follow the final component, so a symlinked
    intermediate directory would otherwise let a declared interface resolve to a
    file outside the module (or outside `--modules-dir` entirely) and be counted
    as an approved surface. A bare directory with no `__init__.py` does not
    resolve either -- D2 names the package form as `<path>/__init__.py`
    specifically, and the whole-package-as-interface shape is already refused by
    `_INTERFACE_PATH_RE` requiring at least one dot below the module."""
    current = module_dir
    for part in parts[:-1]:
        current = current / part
        kind = _manifest_path_kind(current, context)
        if kind == "symlink":
            raise GateInputError(f"{context}: resolves through a symlink at {current} (refused)")
        if kind != "dir":
            return None
    leaf = parts[-1]
    for candidate in (current / f"{leaf}.py", current / leaf / "__init__.py"):
        # The package form's own directory is checked implicitly: `lstat` on
        # `<leaf>/__init__.py` raises ENOTDIR/ENOENT when `<leaf>` is a file or
        # absent, both of which `_manifest_path_kind` maps to "missing". A
        # symlinked `<leaf>` directory is caught by the explicit check below,
        # because `lstat` would then follow it to report on `__init__.py`.
        parent_kind = _manifest_path_kind(candidate.parent, context)
        if parent_kind == "symlink":
            raise GateInputError(
                f"{context}: resolves through a symlink at {candidate.parent} (refused)"
            )
        kind = _manifest_path_kind(candidate, context)
        if kind == "symlink":
            raise GateInputError(f"{context}: {candidate} is a symlink (refused)")
        if kind == "file":
            return candidate
    return None


def _external_ref_conflict(
    ref: str,
    default_schema: str,
    seen_schemas: Mapping[str, str],
    all_prefixes: Sequence[tuple[str, str]],
) -> tuple[str, str] | None:
    """ADR-011 D3.5/b1: `external_table_references` is a declaration, never an
    exemption. Returns `(conflicting_owner, descriptor)` if `ref` resolves to
    any declared module's `owned_schemas` or `owned_table_prefixes` -- including
    the declaring module's own -- else `None`. Resolution follows D3.3's own
    precedence (rule 2): a 2-part `schema.table` ref is resolved by
    `owned_schemas` unless `schema` equals `default_schema`, in which case it is
    stripped and the remainder is resolved by prefix exactly like a real
    identifier -- otherwise wrapping an owned prefix in the default schema would
    bypass this check entirely."""
    parts = ref.split(".", 1)
    if len(parts) == 2:
        schema_part, table_part = parts
        if schema_part != default_schema:
            owner = seen_schemas.get(schema_part)
            if owner is not None:
                return owner, f"owned_schemas entry {schema_part!r}"
            return None
    else:
        table_part = parts[0]
    for owner, prefix in all_prefixes:
        if table_part.startswith(prefix):
            return owner, f"owned_table_prefixes entry {prefix!r}"
    return None


def parse_module_manifest(
    raw: Any, modules_root: str, modules_dir: Path
) -> tuple[dict[str, ModuleEntry], str]:
    """Module-dependency manifest (version 1). ADR-011 D1/D2 fixes this gate's
    input-contract *schema* (this function). Three manifest-level D3 invariants
    are also enforced here (GATE2-R1-D1A-MANIFEST-COMPLETION-2026-10-05.md):
    owned_schemas reserved values (D3.4), owned_schemas disjoint from
    default_schema (D3.3(3)), and external_table_references never resolving to
    any declared module's owned prefix/schema (D3.5).

    Returns `(modules, default_schema)` -- GATE2-R1-D1A-SCANNER-WIRING-2026-10-05:
    `default_schema` must reach the live SQL-scanning call to
    `attribute_table_identifier` (D3.3 rule 2), so it is returned alongside the
    module map rather than parsed-and-discarded as the two prior D1a increments
    left it. This is an additive return-shape change from the prior two D1a
    increments (which returned only `dict[str, ModuleEntry]`); every call site in
    this file and its test module is updated accordingly.

    `modules_dir` is required, not optional-with-default, because D2's
    interface-existence rule (R1-F13) needs the real tree and a `None` default
    would make "caller forgot to thread the root" silently equivalent to "skip
    the check" -- the fail-open shape this rule exists to close."""
    if not isinstance(raw, dict):
        raise GateInputError("module manifest must be a JSON object")
    extra_top = sorted(set(raw) - _TOP_LEVEL_ALLOWED)
    if extra_top:
        raise GateInputError(f"module manifest has unsupported top-level key(s) {extra_top}")
    missing_top = sorted(_TOP_LEVEL_REQUIRED - set(raw))
    if missing_top:
        raise GateInputError(f"module manifest missing required top-level key(s) {missing_top}")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise GateInputError(f"module manifest version {raw['version']!r} != 1")
    # ADR-011 D2: optional, top-level, default "public". Not yet threaded into any
    # resolution logic (that is D3.3, out of scope here) — accepted and schema-
    # validated only, so a manifest author may rely on the field existing.
    default_schema = raw.get("default_schema", "public")
    if not (isinstance(default_schema, str) and _MODULE_NAME_IDENT_RE.fullmatch(default_schema)):
        raise GateInputError(f"default_schema {default_schema!r} is not a valid identifier")
    modules = raw["modules"]
    if not isinstance(modules, dict) or not modules:
        raise GateInputError("module manifest 'modules' must be a non-empty object")
    out: dict[str, ModuleEntry] = {}
    seen_domains: dict[str, str] = {}
    seen_schemas: dict[str, str] = {}
    all_prefixes: list[tuple[str, str]] = []
    all_ext_refs: list[tuple[str, str]] = []
    for name, entry in modules.items():
        # ADR-011 D4/b5/c4: the reserved-importer set, not only `_shared` — `_root`
        # fully matches `_MODULE_NAME_IDENT_RE` and must be refused here too.
        if name in _RESERVED_MODULE_NAMES:
            raise GateInputError(f"module manifest may not name a module {name!r} (reserved)")
        # ADR-011 D2/R1-F08: the module key itself must be a valid identifier —
        # closes the dotted/non-identifier-name gap `target.split(".", 1)[0]`
        # resolution alone does not catch.
        if not _MODULE_NAME_IDENT_RE.fullmatch(name):
            raise GateInputError(
                f"module name {name!r} is not a valid identifier (must fullmatch "
                "^[a-z_][a-z0-9_]*$)"
            )
        if not isinstance(entry, dict):
            raise GateInputError(f"module {name!r} entry must be an object")
        extra = sorted(set(entry) - _MODULE_ENTRY_KEYS)
        if extra:
            raise GateInputError(f"module {name!r} has unsupported key(s) {extra}")
        missing = sorted(set(_MODULE_ENTRY_REQUIRED) - set(entry))
        if missing:
            raise GateInputError(f"module {name!r} missing required key(s) {missing}")
        domain = entry["domain"]
        if not (isinstance(domain, str) and _DOMAIN_CODE_RE.fullmatch(domain)):
            raise GateInputError(f"module {name!r} domain {domain!r} is not DDD-NN")
        if domain in seen_domains:
            raise GateInputError(
                f"domain {domain!r} is owned by both {seen_domains[domain]!r} and {name!r}"
            )
        seen_domains[domain] = name
        prefixes = _manifest_str_list(entry, "owned_table_prefixes", name)
        if not prefixes:
            raise GateInputError(f"module {name!r} owned_table_prefixes must be non-empty")
        schemas = _manifest_str_list(entry, "owned_schemas", name)
        interfaces = _manifest_str_list(entry, "public_interfaces", name)
        if not interfaces:
            raise GateInputError(f"module {name!r} public_interfaces must be non-empty")
        # ADR-011 D2: optional, default []. Schema-validated as "concrete identifiers
        # only, no wildcards" (D3.5's own phrasing); the D3.5 cross-check that an
        # entry may not name another module's owned prefix/schema is attribution
        # logic (D3/I-2) and is deferred — see the stabilization checkpoint.
        ext_refs = _manifest_str_list(entry, "external_table_references", name)
        for ref in ext_refs:
            if not _EXTERNAL_REF_RE.fullmatch(ref):
                raise GateInputError(
                    f"module {name!r} external_table_references entry {ref!r} must be a "
                    "concrete 1- or 2-part identifier (no wildcards)"
                )
            # ADR-011 D3.5/b1: the ownership cross-check runs once every module's
            # owned_table_prefixes/owned_schemas are known (below, after this loop) --
            # queued here, not checked inline, because a reference may name a module
            # declared later in manifest order, or the declaring module's own entry.
            all_ext_refs.append((name, ref))
        seen_prefixes_this_module: set[str] = set()
        for prefix in prefixes:
            # ADR-011 D2/b3: the prefix floor is `+`, not `*` — "at least two
            # characters before a mandatory trailing underscore".
            if not _PREFIX_FLOOR_RE.fullmatch(prefix):
                # R1-F12: the pattern quoted in the named ERROR is read off the regex
                # that was actually applied, never restated as a second literal. The
                # prior form hardcoded "^[a-z][a-z0-9_]+_$" in the message, so a future
                # weakening of `_PREFIX_FLOOR_RE` (b3's `+` -> `*` regression, which is
                # exactly what lets `a_` claim an unbounded namespace) would have left
                # this ERROR asserting a floor the gate did not enforce. Output is
                # byte-identical for the current pattern -- this narrows the message's
                # trust surface, it does not change which prefixes are denied.
                raise GateInputError(
                    f"module {name!r} owned_table_prefixes entry {prefix!r} does not satisfy "
                    f"the prefix floor ({_PREFIX_FLOOR_RE.pattern} -- at least two characters "
                    "before the trailing underscore)"
                )
            # ADR-011 D3.4: reserved values refused at parse time (checked after the
            # floor, not instead of it — `pg_` satisfies the floor and must still be
            # caught here, exactly the case the ADR calls out by name).
            if prefix in _RESERVED_MANIFEST_VALUES:
                raise GateInputError(
                    f"module {name!r} owned_table_prefixes entry {prefix!r} is a reserved value"
                )
            if prefix in seen_prefixes_this_module:
                raise GateInputError(
                    f"module {name!r} has duplicate owned_table_prefixes entry {prefix!r}"
                )
            seen_prefixes_this_module.add(prefix)
            all_prefixes.append((name, prefix))
        for schema in schemas:
            if not _MODULE_NAME_IDENT_RE.fullmatch(schema):
                raise GateInputError(f"module {name!r} owned_schemas entry {schema!r} "
                                     "is not a valid identifier")
            # ADR-011 D3.4: "pg_, pg_catalog, pg_temp and information_schema are
            # rejected at parse time as owned_table_prefixes OR owned_schemas
            # values" -- the same reserved set applies to both fields.
            if schema in _RESERVED_MANIFEST_VALUES:
                raise GateInputError(
                    f"module {name!r} owned_schemas entry {schema!r} is a reserved value "
                    "(ADR-011 D3.4)"
                )
            # ADR-011 D3.3(3)/b2(i): owned_schemas must be disjoint from
            # default_schema, enforced at parse time -- without this, a module
            # declaring default_schema as an owned_schemas entry would capture
            # every bare table under it as state-1 clean (b2's fail-open).
            if schema == default_schema:
                raise GateInputError(
                    f"module {name!r} owned_schemas entry {schema!r} must not equal "
                    f"default_schema {default_schema!r} -- owned_schemas must be disjoint "
                    "from default_schema (ADR-011 D3.3(3))"
                )
            if schema in seen_schemas:
                raise GateInputError(
                    f"schema {schema!r} is owned by both {seen_schemas[schema]!r} and {name!r}"
                )
            seen_schemas[schema] = name
        prefix_req = f"{modules_root}.{name}."
        # ADR-011 D2/R1-F13: existence is verified inside the module's *own*
        # directory, and only when that directory is really there. A
        # manifest-declared-but-absent module stays the D5.6 note it already is
        # ("a manifest-declared-but-absent module remains a note, not an ERROR")
        # rather than becoming an ERROR by way of its unverifiable interfaces --
        # that carve-out is the one residual of this rule; the coverage note
        # already discloses the `no_dir` note itself (D5.6), and the module
        # docstring now names the unverified-interface consequence that follows
        # from it. `_manifest_path_kind` is used rather
        # than `is_dir()` because the absence branch skips validation, so an
        # `EACCES` swallowed into "absent" would widen the approved surface.
        module_dir = modules_dir / name
        module_dir_kind = _manifest_path_kind(
            module_dir, f"module {name!r} directory {module_dir}"
        )
        for iface in interfaces:
            if not (_INTERFACE_PATH_RE.fullmatch(iface) and iface.startswith(prefix_req)):
                raise GateInputError(
                    f"module {name!r} public_interfaces entry {iface!r} must be a dotted path "
                    f"strictly under {prefix_req!r}"
                )
            if module_dir_kind != "dir":
                continue  # D5.6 carve-out above; a symlinked dir is refused by _discover_modules
            remainder = iface[len(prefix_req):].split(".")
            context = f"module {name!r} public_interfaces entry {iface!r}"
            if _resolve_interface_target(module_dir, remainder, context) is None:
                rel = "/".join(remainder)
                raise GateInputError(
                    f"{context} does not resolve to an existing module file or package "
                    f"under {module_dir} (expected {rel}.py or {rel}/__init__.py) -- "
                    "ADR-011 D2: a typo must narrow the approved surface, never widen it"
                )
        out[name] = ModuleEntry(name, domain, tuple(prefixes), tuple(schemas), tuple(interfaces),
                                tuple(ext_refs))
    # ADR-011 D2 (duplicate/overlap detection): unchanged from the pre-stabilization
    # implementation — preserved exactly, not weakened or extended by this step.
    for i, (mod_a, pre_a) in enumerate(all_prefixes):
        for mod_b, pre_b in all_prefixes[i + 1:]:
            # Overlap is only *ambiguous* across two different modules. One module
            # may own nested prefixes ('cal_' and 'cal_event_'): the owner is the
            # same either way, and that is the only shape under which rule 5's
            # "longest matching owned_table_prefixes" is a live resolution rule.
            if mod_a == mod_b:
                continue
            if pre_a.startswith(pre_b) or pre_b.startswith(pre_a):
                raise GateInputError(
                    f"ambiguous table prefix ownership: {mod_a!r}:{pre_a!r} and "
                    f"{mod_b!r}:{pre_b!r} overlap"
                )
    # ADR-011 D3.5/b1: an external_table_references entry may not resolve to any
    # declared module's owned_table_prefixes or owned_schemas -- including the
    # declaring module's own -- checked now that every module's prefixes/schemas
    # are known. Declaring another module's (or your own) owned table as
    # "external" would otherwise be a manifest-layer allowlist over the gate's
    # headline invariant (the tool's own contract: "no skip, exempt, or
    # allowlist path").
    for owner_name, ref in all_ext_refs:
        conflict = _external_ref_conflict(ref, default_schema, seen_schemas, all_prefixes)
        if conflict is not None:
            conflicting_owner, descriptor = conflict
            raise GateInputError(
                f"module {owner_name!r} external_table_references entry {ref!r} resolves "
                f"to {descriptor} owned by {conflicting_owner!r} (ADR-011 D3.5 -- not an "
                "exemption)"
            )
    return out, default_schema


def load_module_manifest(
    path: Path, modules_root: str, modules_dir: Path
) -> tuple[dict[str, ModuleEntry], str]:
    """Missing or symlinked manifest is ERROR; no CLI flag can substitute this check.
    Returns `(modules, default_schema)` -- see `parse_module_manifest`."""
    if path.is_symlink() or not path.is_file():
        raise GateInputError(f"module manifest {path} missing or a symlink")
    return parse_module_manifest(_load_json(path), modules_root, modules_dir)


def _modules_root_package(modules_dir: Path) -> str:
    """Dotted package path of `modules_dir`, walking parents while `__init__.py`
    exists (e.g. `backend/app/modules` -> `app.modules`)."""
    if modules_dir.is_symlink() or not modules_dir.is_dir():
        raise GateInputError(f"modules directory {modules_dir} not found or is a symlink")
    if not (modules_dir / "__init__.py").is_file():
        raise GateInputError(f"modules directory {modules_dir} has no __init__.py")
    segments = [modules_dir.name]
    current = modules_dir.parent
    while (current / "__init__.py").is_file():
        segments.append(current.name)
        current = current.parent
    return ".".join(reversed(segments))


def _discover_modules(modules_dir: Path) -> list[str]:
    """Immediate child directories with `__init__.py`, excluding `__pycache__`,
    dot-prefixed names and `_shared`."""
    names = []
    for entry in sorted(modules_dir.iterdir()):
        if entry.name in ("__pycache__", SHARED_PACKAGE) or entry.name.startswith("."):
            continue
        if entry.is_symlink():
            raise GateInputError(f"{entry}: symlinks are refused")
        if entry.is_dir() and (entry / "__init__.py").is_file():
            names.append(entry.name)
    return names


@dataclass
class _FileAccounting:
    """ADR-011 D8's file-accounting counters -- "files inspected, inert, pruned by
    reason, and at the modules-root" (GATE2-R1-F12-D8-FILE-COUNTS-2026-10-05).
    Mutated in place by `_walk_module` and by `run_module_deps_gate`'s per-file
    scan loop, and held outside that function's `try` for the same reason
    `_TableRefCounts` and `_ImportEdgeCounts` are: whatever the run really
    established must survive into the ERROR report built by the
    `except GateInputError` handler, labelled as a minimum rather than discarded
    with the frame or read as a total.

    `attempted` and `inspected` are deliberately two fields, not one. A file is
    *attempted* when the scan classified it as substantive and committed to
    opening it (the same moment it joins the report's `checked` list);
    it is *inspected* only once its own analysis ran to completion. They are
    equal on every path that does not abort -- an uninspectable finding or a real
    violation does not stop the loop -- and diverge by exactly the aborting file
    on the `GateInputError` path, which is the one place a single figure would
    have had to overstate one or the other.

    `root_files` is `None` until `_root_level_files` has actually returned, which
    is the same discriminator `declared_external` uses: a run that aborted before
    the modules-root listing must disclose UNKNOWN, never a zero that would read
    as "the modules root holds no file".

    `walk_started` distinguishes "no module/`_shared` walk ever ran" from "the
    walks ran and pruned nothing", so the two prune figures below are never
    reported as a complete zero by a run that never looked. They count the
    *recursive* scan surface only -- the top-level listing's own prunes are the
    D5 pass's `_CoverageCounts.pruned_pycache`/`pruned_dot`, counted there and
    never re-counted here, since the two traversals cover disjoint territory and
    summing them would double-count nothing while claiming a tree-wide total
    neither establishes."""
    inert: int = 0
    attempted: int = 0
    inspected: int = 0
    root_files: int | None = None
    walk_started: bool = False
    walk_pruned_pycache: int = 0
    walk_pruned_dot: int = 0


def _walk_module(mod_dir: Path, acct: _FileAccounting | None = None) -> list[Path]:
    """Every regular file under `mod_dir`, pruning `__pycache__`/dot-directories
    without descending into them. Any symlink anywhere else is ERROR.

    `acct` is ADR-011 D8's file-accounting sink
    (GATE2-R1-F12-D8-FILE-COUNTS-2026-10-05): when supplied, this walk records
    that it ran and counts each pruned directory entry under its own reason, so a
    report can disclose "pruned by reason" for the recursive scan surface and not
    only for the D5 pass's top-level listing. Mutated in place, so a walk that
    raises mid-traversal leaves the caller holding the prunes it had already made
    -- an observed minimum rather than a count discarded with the frame.
    Counting is the *only* thing `acct` does here: no pruning, inclusion or
    refusal decision reads it, so a `None` sink and a supplied one return
    identical file lists."""
    files: list[Path] = []
    if acct is not None:
        acct.walk_started = True
    stack = [mod_dir]
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir()):
            if (entry.is_dir() and not entry.is_symlink()
                    and (entry.name == "__pycache__" or entry.name.startswith("."))):
                if acct is not None:
                    # Disjoint by construction: `__pycache__` does not start with a dot.
                    if entry.name == "__pycache__":
                        acct.walk_pruned_pycache += 1
                    else:
                        acct.walk_pruned_dot += 1
                continue
            if entry.is_symlink():
                raise GateInputError(f"{entry}: symlinks are refused")
            if entry.is_dir():
                stack.append(entry)
            elif entry.is_file():
                files.append(entry)
            else:
                raise GateInputError(f"{entry}: not a regular file")
    return files


def _root_level_files(modules_dir: Path) -> list[Path]:
    """ADR-011 D4 (GATE2-R1-D4-ROOT-FILE-SCAN-2026-10-05): direct, non-recursive
    files under `modules_dir` itself -- the `_root` importer's scan surface. A
    directory entry (a discovered module, `_shared`, `__pycache__`, a
    dot-directory) is skipped without descending: those are all handled by
    `_discover_modules`/`_walk_module` separately, so root scanning is direct
    files only. Any symlink is ERROR, identically to `_walk_module`. No
    dot-*file* skip is applied here -- `_walk_module` does not skip dot-files
    either, so an unrecognised root-level dot-file reaching `_categorize` and
    ERRORing is the same fail-closed property module directories already
    have."""
    files: list[Path] = []
    for entry in sorted(modules_dir.iterdir()):
        if entry.is_dir() and not entry.is_symlink():
            continue
        if entry.is_symlink():
            raise GateInputError(f"{entry}: symlinks are refused")
        if entry.is_file():
            files.append(entry)
        else:
            raise GateInputError(f"{entry}: not a regular file")
    return files


def _categorize(path: Path) -> str:
    """The recognised file-type set is deliberately closed; anything else is ERROR."""
    if path.suffix == ".py":
        return "python"
    if path.suffix == ".sql":
        return "sql"
    if path.name in _INERT_NAMES or path.suffix in _INERT_SUFFIXES:
        return "inert"
    raise GateInputError(f"{path}: unsupported file extension (recognised: .py, .sql, "
                         ".md, .txt, .gitkeep)")


_SOURCE_KIND_LABELS = {"python": "Python source", "sql": "SQL source"}


def _read_source_text(path: Path, relpath: str, kind: str) -> str:
    """The module-deps scan's `_read_gate_text` wrapper: it supplies the source-file
    `what` label and nothing else, so D7.3's conversion stays in exactly one place
    for every substantive source file the scan opens (R1-F07): `OSError`,
    `UnicodeDecodeError` and `ValueError` become `GateInputError`, which
    `run_module_deps_gate` reports as `MODULE_DEPS_GATE_INPUT_INVALID` ERROR at
    exit 2 -- never an uncaught traceback with exit 1 and no `GateReport` at
    all, which is what the bare `path.read_text(encoding="utf-8")` at each scan
    site produced (both reproduced by direct execution before their increments:
    the `.py` site first, then the `.sql` site by
    GATE2-R1-F07-SQL-DECODE-ERROR-2026-10-05).

    A non-UTF-8 `.py` file is ERROR *even when it is legal Python* under a
    PEP 263 coding cookie (`# -*- coding: latin-1 -*-`, confirmed by
    `py_compile` on the fixture). Honouring the cookie would mean a second
    decode path and a wider input contract than D7.3 settles, so the
    fail-closed answer here is "unusable input, inspect nothing", never a
    silent re-decode and never a skip. A non-UTF-8 `.sql` file gets the same
    answer for the same reason -- there is no SQL analogue of the coding
    cookie to even consider honouring, and a byte sequence the gate cannot
    decode is a byte sequence whose table references it cannot attribute, so
    ERROR rather than a silent `errors="replace"` that would scan corrupted
    text and could report PASS over it. The type name is included because
    decode failure and `EACCES` are otherwise indistinguishable in the report.

    `kind` is the `_categorize` discriminator, used only to name the file class
    in the message; an unrecognised value degrades to naming it verbatim rather
    than raising, since this helper's job is to convert failures, not add one.
    """
    return _read_gate_text(path, relpath, _SOURCE_KIND_LABELS.get(kind, f"{kind} source"))


def _scan_namespace_subtree(root: Path,
                            counts: _CoverageCounts | None = None) -> tuple[int, Path | None]:
    """ADR-011 D5.2/D5.4: recursively inspects a non-discovered directory under
    `--modules-dir` (no `__init__.py`, so `_discover_modules` silently dropped
    it -- R1-F04's exact shape) to decide whether it is forced to
    `MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH`. Uses `os.scandir` and
    `os.DirEntry.is_dir(follow_symlinks=False)` / `is_file(follow_symlinks=False)`
    rather than `Path.is_dir()` / `Path.is_file()` -- the latter catch *every*
    `OSError` (confirmed by direct execution: `os.path.isdir`'s own
    `except (OSError, ValueError): return False`), including `EACCES`, and
    would silently treat an unreadable namespace directory as empty -- the
    exact fail-open shape SCN-070 already found on another surface (ADR-011
    D5.4). Any `OSError` raised while enumerating is converted to
    `GateInputError` here, following `_load_json`'s own conversion idiom,
    rather than being swallowed or left to escape uncaught. Mirrors
    `_walk_module`'s own pruning (`__pycache__`/dot directories are skipped
    without descending) and symlink refusal (D5.3) -- this is new territory
    `_walk_module` never visits, since the directory was never discovered as
    a module. Returns `(inert_file_count, first_non_inert_file_or_None)`; the
    walk short-circuits on the first non-inert file found, because the caller
    only needs one witness to ERROR the whole run.

    `counts` is ADR-011 D8's accounting sink for this probe
    (GATE2-R1-F12-D8-NAMESPACE-FILE-PRUNE-COUNTS-2026-10-06): when supplied, the
    inert files it counts and the directory entries it prunes -- split by reason --
    are recorded on it as they are observed, so the D8 file-accounting note can
    disclose this traversal's own file and prune surface instead of excluding it in
    prose. Recording happens at the moment of each observation and the object is
    mutated in place, so a probe that short-circuits on a non-inert file or aborts
    on an `OSError` leaves the caller holding what it had really seen -- an
    observation up to that point, never a subtree total. Counting is the *only*
    thing `counts` does here: no prune, descend, inert, refusal or short-circuit
    decision reads it, and the returned tuple is identical with and without it."""
    inert_count = 0
    stack = [root]
    try:
        while stack:
            current = stack.pop()
            with os.scandir(current) as it:
                entries = sorted(it, key=lambda e: e.name)
            for entry in entries:
                if entry.is_symlink():
                    raise GateInputError(f"{entry.path}: symlinks are refused")
                if entry.is_dir(follow_symlinks=False):
                    if entry.name == "__pycache__" or entry.name.startswith("."):
                        if counts is not None:
                            # ADR-011 D8, this probe's own by-reason pair. Disjoint by
                            # construction, exactly as in `_walk_module` and the D5
                            # top-level listing: `__pycache__` does not start with a dot.
                            if entry.name == "__pycache__":
                                counts.namespace_probe_pruned_pycache += 1
                            else:
                                counts.namespace_probe_pruned_dot += 1
                        continue  # pruned-and-counted, identical to `_walk_module` --
                        # a dot-*directory*, never a dot-*file* (a dot-file like
                        # `.gitkeep` must still reach the inert check below, exactly
                        # as `_walk_module` itself never skips dot-files).
                    stack.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    raise GateInputError(f"{entry.path}: not a regular file")
                path = Path(entry.path)
                if path.suffix in _INERT_SUFFIXES or path.name in _INERT_NAMES:
                    inert_count += 1
                    if counts is not None:
                        # ADR-011 D8: the same increment the return value carries, so the
                        # disclosed figure and the caller's bucket have one producer and
                        # cannot drift. Unconditional on the short-circuit below, unlike
                        # the caller's own `namespace_inert` bucket.
                        counts.namespace_probe_inert += 1
                    continue
                return inert_count, path
    except OSError as exc:
        raise GateInputError(
            f"{root}: cannot enumerate ({type(exc).__name__}: {exc})"
        ) from None
    return inert_count, None


def _enumerate_eligible_descendants(root: Path) -> list[Path]:
    """ADR-011 D5.1 recursive coverage reconciliation: a fresh, fully
    independent recursive traversal of `root`'s entire subtree -- it does
    not call `_walk_module`, does not reuse its return value, and shares no
    cache with it, which is the entire point of reconciling one walk against
    another. Mirrors `_walk_module`'s own inclusion rule exactly (pruning
    `__pycache__`/dot-prefixed *directories* without descending; dot-*files*
    are not pruned) so that a correct walk diffs to zero against this one.
    Uses `os.scandir` and `os.DirEntry.is_dir(follow_symlinks=False)` /
    `is_file(follow_symlinks=False)` exclusively -- never `Path.exists()` /
    `Path.is_dir()` / `Path.is_file()` to decide *whether* to scan (D5.4),
    for the same `EACCES`-fail-open reason `_scan_namespace_subtree` already
    documents. Any symlink anywhere is refused (D5.3). Any `OSError` raised
    while enumerating is converted to `GateInputError`, following
    `_scan_namespace_subtree`'s own conversion idiom, rather than swallowed
    or left to escape uncaught. Returns every eligible regular file -- inert
    files included, identically to `_walk_module`'s own return shape -- so
    the caller's diff is a plain set membership check."""
    files: list[Path] = []
    stack = [root]
    try:
        while stack:
            current = stack.pop()
            with os.scandir(current) as it:
                entries = sorted(it, key=lambda e: e.name)
            for entry in entries:
                if entry.is_symlink():
                    raise GateInputError(f"{entry.path}: symlinks are refused")
                if entry.is_dir(follow_symlinks=False):
                    if entry.name == "__pycache__" or entry.name.startswith("."):
                        continue  # pruned, identical to `_walk_module`
                    stack.append(Path(entry.path))
                    continue
                if entry.is_file(follow_symlinks=False):
                    files.append(Path(entry.path))
                    continue
                raise GateInputError(f"{entry.path}: not a regular file")
    except OSError as exc:
        raise GateInputError(
            f"{root}: cannot enumerate ({type(exc).__name__}: {exc})"
        ) from None
    return files


def _reconcile_subtree_against_walk(
    root: Path, owner: str, modules_dir: Path, walked_relpaths: set[str],
) -> tuple[set[str], list[Violation]]:
    """ADR-011 D5.1: the recursive half of the reconciliation. Independently
    re-enumerates `root` (a discovered module directory, or `_shared`) via
    `_enumerate_eligible_descendants` and diffs every eligible path against
    `walked_relpaths` -- the real union `run_module_deps_gate` already
    assembled from `_walk_module` via `scan_units`, supplied by the caller,
    never recomputed here. Every eligible path absent from that union is
    `MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH`, naming `owner` -- this is what
    turns a `_walk_module`/discovery omission inside an already-recognised
    subtree into an ERROR instead of a silent PASS (the residual named in
    GATE2-R1-F04-NAMESPACE-COVERAGE-VERIFICATION-2026-10-05.md's Limits).
    Returns `(enumerated_relpaths, violations)`: the relpath set is returned
    (not merely counted) so the caller can run D5.1's *reverse* diff --
    walked-minus-independently-eligible -- against the union of every
    subtree's eligible set plus the modules-root files, which no single
    subtree can decide on its own."""
    eligible = _enumerate_eligible_descendants(root)
    violations: list[Violation] = []
    enumerated: set[str] = set()
    for path in eligible:
        try:
            relpath = path.relative_to(modules_dir).as_posix()
        except ValueError as exc:
            # D5.6: a path this traversal reached that is not under the
            # supplied --modules-dir is the fixture-containment boundary --
            # fail closed rather than silently drop it from the diff.
            raise GateInputError(
                f"{path}: enumerated path is not under {modules_dir} (ADR-011 D5.6)"
            ) from exc
        enumerated.add(relpath)
        if relpath not in walked_relpaths:
            violations.append(Violation(
                "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH", relpath,
                f"{owner!r} subtree contains a path the module walk never reached "
                "(ADR-011 D5.1 recursive coverage reconciliation) -- a "
                "_walk_module/discovery omission inside an already-recognised "
                "module or _shared subtree, reported here instead of silently "
                "passing",
            ))
    return enumerated, violations


@dataclass
class _CoverageCounts:
    """ADR-011 D5.5/D8 bucket counters, mutated in place by the single
    reconciliation pass rather than held as separate locals, so that a pass
    which aborts mid-enumeration can still disclose exactly what it had
    established -- as a labelled lower bound -- instead of disclosing
    nothing. Reporting nothing is the shape D5.5/D8 forbid; reporting these
    as if they were complete totals would be worse, so the partial renderer
    below never does."""
    modules: int = 0
    shared: int = 0
    root_files: int = 0
    # ADR-011 D8's "pruned by reason" (GATE2-R1-F12-D8-FILE-COUNTS-2026-10-05). The
    # single `pruned` aggregate this pass carried is now the *derived* sum of the two
    # reasons it was ever incremented for, so the by-reason split and the existing
    # D5.5 aggregate have exactly one producer and cannot drift apart. The aggregate's
    # rendering in `_coverage_count_clause` is unchanged, byte for byte.
    pruned_pycache: int = 0
    pruned_dot: int = 0
    namespace_inert: int = 0
    recursive_eligible: int = 0
    # ADR-011 D8's file/prune accounting for the *third* traversal this gate performs,
    # the D5.2 non-discovered-namespace probe
    # (GATE2-R1-F12-D8-NAMESPACE-FILE-PRUNE-COUNTS-2026-10-06). These five fields are
    # written by `_scan_namespace_subtree` and its call site and read only by
    # `_d8_file_accounting_note`; `_coverage_count_clause` does not render them, so the
    # D5 coverage note is unchanged byte for byte and `namespace_inert` above keeps its
    # own, deliberately different rule (see `namespace_probe_inert`).
    #
    # `namespace_probes` is incremented at the call site *before* each probe runs, so a
    # probe that aborts mid-traversal is still disclosed as attempted; it is also the
    # discriminator that tells "the listing reached no non-discovered directory" (a real
    # zero) from "the listing never ran" (UNKNOWN, carried by `coverage is None`).
    #
    # `namespace_probe_inert` counts every inert file any probe saw, including the
    # probes that then short-circuited on a non-inert file. `namespace_inert` above
    # deliberately does not: the D5 bucket credits a namespace directory's inert files
    # only when that directory holds no non-inert file at all. The two therefore agree
    # on a run where no namespace candidate ERRORed and diverge on one where it did,
    # which is exactly why the probe's own figure is disclosed rather than left to that
    # bucket.
    namespace_probes: int = 0
    namespace_probe_short_circuited: int = 0
    namespace_probe_inert: int = 0
    namespace_probe_pruned_pycache: int = 0
    namespace_probe_pruned_dot: int = 0

    @property
    def pruned(self) -> int:
        """The D5.5 aggregate, derived rather than accumulated: a top-level entry is
        pruned for exactly one of the two reasons, so the sum is the aggregate by
        construction."""
        return self.pruned_pycache + self.pruned_dot


_COVERAGE_RELATIVITY_NOTE = (
    "coverage reconciliation totality is relative to the supplied --modules-dir "
    "only; it asserts nothing about a different root, and a manifest-declared "
    "module with no directory remains the existing 'no_dir' note, not an ERROR "
    "(ADR-011 D5.6)")

_COVERAGE_BOTH_DIRECTIONS_NOTE = (
    "ADR-011 D5.1 recursive coverage reconciliation runs both directions of the "
    "set diff: the unwalked direction (a path independently enumerated inside a "
    "discovered module or _shared subtree but never reached by _walk_module) and "
    "the reverse direction (a path the module/_shared/modules-root walks reached "
    "but this independent enumeration does not find eligible in any of those "
    "buckets); either way the path is ERROR "
    "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH rather than a silent pass")


_COVERAGE_NOT_STARTED = "NOT_STARTED"


def _coverage_count_clause(counts: _CoverageCounts | None) -> str:
    """The bucket-count clause shared by the complete, partial and pre-coverage
    renderers, so they can never drift apart in what they count or how they
    name it.

    `counts is None` is the pre-coverage shape: the reconciliation pass never
    began, so every bucket renders `NOT_STARTED` in the slot a number occupies
    and the number-dependent plural becomes the neutral `y/ies`. It is
    deliberately *not* a zero-filled `_CoverageCounts()` -- a literal `0` in
    these slots would assert that the enumeration looked and found nothing,
    which is exactly the fabricated-total failure mode D5.5 exists to prevent.
    For a real `counts` the rendering is unchanged, byte for byte."""
    def q(attr: str) -> str:
        return _COVERAGE_NOT_STARTED if counts is None else str(getattr(counts, attr))

    def plural(attr: str, one: str, many: str) -> str:
        if counts is None:
            return f"{one}/{many}"
        return one if getattr(counts, attr) == 1 else many

    return (
        f"{q('modules')} module director{plural('modules', 'y', 'ies')}, "
        f"{q('shared')} _shared director{plural('shared', 'y', 'ies')}, "
        f"{q('root_files')} modules-root file(s), "
        f"{q('pruned')} pruned entr{plural('pruned', 'y', 'ies')}, "
        f"{q('namespace_inert')} inert file(s) in inert-only namespace director"
        "y/ies, "
        f"{q('recursive_eligible')} eligible descendant file(s) independently "
        "re-enumerated across discovered-module and _shared subtrees (ADR-011 "
        "D5.1 recursive coverage reconciliation)")


def _dedupe_coverage_violations(violations: list[Violation]) -> list[Violation]:
    """D7.4-style discipline applied to this gate's own coverage ERROR code:
    dedupe (a discovered module and its recursive subtree check can never
    collide today, but dedupe is cheap insurance against a future duplicate
    producer) and sort deterministically by subject, so report ordering never
    depends on os.scandir's incidental yield order across the two
    reconciliation layers. Shared with the partial path so the count it
    discloses is the same deduped count the complete path would report."""
    seen: dict[tuple[str, str, str], Violation] = {}
    for v in violations:
        seen[(v.code, v.subject, v.detail)] = v
    return sorted(seen.values(), key=lambda v: v.subject)


def _pre_coverage_notes() -> list[str]:
    """ADR-011 D5.5/D8 coverage disclosure for a run that aborted *before* the
    reconciliation pass began at all -- e.g. an absent, symlinked or
    `__init__.py`-less `--modules-dir`, or an unusable manifest, each of which
    raises from `_modules_root_package`/`load_module_manifest`/
    `_discover_modules` upstream of `_reconcile_module_coverage`. Those paths
    produced a bare `MODULE_DEPS_GATE_INPUT_INVALID` report with `notes == []`:
    no coverage disclosure in either surface, which is the condition D5.5/D8
    forbid unqualified by outcome ("every run ... discloses ... all D5.1 bucket
    counts").

    The third shape is required because the other two cannot tell this truth.
    `partial=True` would claim counts were "established before the abort" when
    none were, and `partial=False` would assert complete totals. Both would
    need a zero-filled `_CoverageCounts()`, i.e. fabricated zeros asserting the
    enumeration looked and found nothing. So every bucket here is
    `NOT_STARTED`, the unattributed count is `UNKNOWN`, and both directions of
    D5.1's diff are declared not-run. Status and exit code are untouched --
    ERROR at exit 2, fail-closed (D7)."""
    return [
        ("coverage reconciliation (ADR-011 D5) NOT_STARTED -- the run aborted "
         "before the independent coverage enumeration began (cause: the "
         "MODULE_DEPS_GATE_INPUT_INVALID violation reported above), so no "
         "bucket was ever counted and none is reported as zero: "
         f"{_coverage_count_clause(None)}, unattributed path(s) UNKNOWN"),
        ("NEITHER direction of ADR-011 D5.1's set diff ran, so their silence is "
         "not evidence that the two traversals agree, and the absence of "
         "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH here is not evidence that no "
         "unattributed path exists; the run stays ERROR at exit 2 under "
         "MODULE_DEPS_GATE_INPUT_INVALID (ADR-011 D7) and no coverage verdict "
         "is claimed"),
        _COVERAGE_RELATIVITY_NOTE,
    ]


def _coverage_notes(counts: _CoverageCounts, unattributed: int, *,
                    partial: bool) -> list[str]:
    """ADR-011 D5.5/D8 coverage disclosure, in the two shapes a run that
    *reached* the reconciliation pass can have. The third shape -- a run that
    aborted before the pass began -- is `_pre_coverage_notes` above.

    `partial=False` is the complete enumeration: the counts are totals and
    both directions of D5.1's diff ran. `partial=True` is an enumeration that
    aborted (ADR-011 D5.4's `OSError`, a D5.3 symlink refusal, a
    non-regular-file refusal, or D5.6's containment check) and whose
    `GateInputError` is about to become `MODULE_DEPS_GATE_INPUT_INVALID` at
    exit 2. The partial shape deliberately (a) labels every count a lower
    bound, (b) says the unreached buckets are UNKNOWN rather than zero, and
    (c) withdraws the both-directions-ran claim, because the reverse diff runs
    only after the pass completes. Inventing complete counts, or silently
    reusing the complete wording, would make an ERROR report assert coverage
    facts the run never established -- the failure mode D5.5 exists to
    prevent, inverted."""
    if not partial:
        return [
            ("coverage reconciliation (ADR-011 D5): "
             f"{_coverage_count_clause(counts)}, "
             f"{unattributed} unattributed path(s) (ADR-011 D5.1/D5.2 -- ERROR "
             "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH above when nonzero)"),
            _COVERAGE_RELATIVITY_NOTE,
            _COVERAGE_BOTH_DIRECTIONS_NOTE,
        ]
    return [
        ("coverage reconciliation (ADR-011 D5) PARTIAL -- the independent "
         "enumeration aborted before completion (cause: the "
         "MODULE_DEPS_GATE_INPUT_INVALID violation reported above); every count "
         "that follows is a LOWER BOUND established before the abort, never a "
         "complete total, and the buckets the enumeration had not yet reached "
         f"are UNKNOWN rather than zero: {_coverage_count_clause(counts)}, "
         f"{unattributed} unattributed path(s) found before the abort"),
        ("ADR-011 D5.1's reverse direction (walked-minus-independently-"
         "enumerated) did NOT run on this partial enumeration, so its silence "
         "is not evidence that the two traversals agree; the run stays ERROR at "
         "exit 2 under MODULE_DEPS_GATE_INPUT_INVALID (ADR-011 D7) and no "
         "coverage verdict is claimed"),
        _COVERAGE_RELATIVITY_NOTE,
    ]


def _reconcile_module_coverage(
    modules_dir: Path, discovered: set[str], shared_present: bool,
    walked_paths: set[Path], counts_sink: _CoverageCounts | None = None,
) -> tuple[list[Violation], list[str]]:
    """ADR-011 D5: a second, independent enumeration of `--modules-dir`'s
    immediate children -- a fresh `os.scandir` call, not a reuse of
    `_discover_modules`'s own listing or return value -- reconciled against
    what `_discover_modules`/`_walk_module`/`_root_level_files` already
    decided. Every entry lands in exactly one bucket (module, `_shared`,
    modules-root file, pruned, namespace-inert, or unattributed ERROR) by
    construction of the single-pass branching below: each entry is visited
    once and exactly one branch below accepts it, which is what turns a
    discovery bug into an ERROR instead of a silent omission (closes R1-F04).

    D5.4: no `Path.is_dir()` / `Path.is_file()` / `Path.exists()` gates
    *whether* a scan happens here -- `os.DirEntry.is_dir(follow_symlinks=False)`
    / `is_file(follow_symlinks=False)` are used instead, and `OSError` is
    converted to `GateInputError` (never swallowed to decide "not a module,
    skip it"). D5.3: a top-level symlink is refused identically to
    `_discover_modules`'s own check, which this function's caller has already
    run and which raises unconditionally on any top-level symlink before this
    function is ever reached -- the check here is defence in depth, not the
    first line of defence, for a top-level entry; `_scan_namespace_subtree`'s
    own symlink refusal below the top level is the branch D5.3 is actually
    aimed at, since a symlink nested inside a non-discovered directory is new
    territory no existing function visits.

    D5.1's "reconciled against the union" is implemented in two layers now:
    mutually-exclusive single-pass bucketing over the top-level listing that
    feeds discovery (module / `_shared` / modules-root file / pruned /
    namespace candidate), PLUS, for each discovered module directory and for
    `_shared`, a second and genuinely independent recursive enumeration
    (`_enumerate_eligible_descendants`, via `_reconcile_subtree_against_walk`)
    diffed against `walked_paths` -- the real walked-path union the caller
    already assembled via `_walk_module`/`scan_units`. Every eligible path
    absent from that union is `MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH`
    (ADR-011 D5.1), closing the residual the R1-F04 implementation record
    named: a discovery/walk bug *inside* an already-recognised module or
    `_shared` subtree no longer silently passes.

    **Both directions of D5.1's set diff now run.** The forward direction
    (independently-eligible minus walked) is the per-subtree diff above. The
    reverse direction (walked minus independently-eligible) is diffed once,
    after the single top-level pass, against the union of every discovered
    module's and `_shared`'s independently-enumerated eligible paths plus the
    modules-root files this function's own `os.scandir` pass found -- i.e.
    exactly the three buckets `scan_units` draws its walked paths from. A
    path the walk reached that the second enumeration does not find eligible
    in any of those buckets is `MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH` too:
    "every path lands in exactly one bucket" (D5.1) is only a reconciliation
    if *neither* side may carry a path the other cannot account for, so the
    reverse direction cannot be left to the walk's own say-so. It must be
    computed here rather than inside `_reconcile_subtree_against_walk`,
    because no single subtree can tell whether a walked path it does not own
    belongs to a sibling module, to `_shared`, or to nothing at all.

    **D5.5 survives an abort.** Any `GateInputError` this pass raises or
    propagates (D5.4's `OSError`, a D5.3 symlink refusal, a non-regular-file
    refusal, D5.6's containment check) leaves with the bucket counts
    established so far attached to it as `notes`, rendered in the partial
    shape `_coverage_notes` defines -- lower bounds, unreached buckets
    declared UNKNOWN, and the both-directions-ran claim withdrawn. Without
    this, a coverage ERROR produced a bare `MODULE_DEPS_GATE_INPUT_INVALID`
    report carrying no coverage disclosure at all, which is the exact
    condition D5.5/D8 forbid; with it, the run still fails closed at ERROR
    exit 2 and no count is invented for work that never happened.

    `counts_sink` is ADR-011 D8's by-reason prune accessor
    (GATE2-R1-F12-D8-FILE-COUNTS-2026-10-05): a caller that needs the top-level
    prune split for its own report supplies the `_CoverageCounts` this pass will
    mutate, so the figure the D8 file-accounting note discloses is literally the
    one this pass counted rather than a second, independently recomputed figure
    that could agree with the code while disagreeing with the D5 note. Supplying
    it changes nothing about this pass's own behaviour, bucketing or return
    value; omitting it is the previous behaviour exactly."""
    walked_relpaths = {p.relative_to(modules_dir).as_posix() for p in walked_paths}
    violations: list[Violation] = []
    # Union of every bucket the second, independent enumeration accepts as
    # eligible: discovered-module descendants, `_shared` descendants, and
    # modules-root files. The reverse diff below is `walked_relpaths` minus
    # this set, so a bucket omitted here would turn into a false ERROR --
    # which is the fail-closed direction, never a silent pass.
    enumerated_relpaths: set[str] = set()
    counts = _CoverageCounts() if counts_sink is None else counts_sink

    def partial_notes() -> list[str]:
        """D5.5 disclosure for an aborted pass -- deduped exactly as the
        complete path would count it, so the two cannot disagree."""
        return _coverage_notes(
            counts, len(_dedupe_coverage_violations(violations)), partial=True
        )

    try:
        with os.scandir(modules_dir) as it:
            entries = sorted(it, key=lambda e: e.name)
    except OSError as exc:
        raise GateInputError(
            f"{modules_dir}: cannot enumerate ({type(exc).__name__}: {exc})",
            notes=partial_notes(),
        ) from None
    try:
        for entry in entries:
            if entry.name in discovered:
                counts.modules += 1
                rels, vs = _reconcile_subtree_against_walk(
                    Path(entry.path), entry.name, modules_dir, walked_relpaths
                )
                counts.recursive_eligible += len(rels)
                enumerated_relpaths |= rels
                violations += vs
                continue
            if entry.name == SHARED_PACKAGE and shared_present:
                counts.shared += 1
                rels, vs = _reconcile_subtree_against_walk(
                    Path(entry.path), SHARED_PACKAGE, modules_dir, walked_relpaths
                )
                counts.recursive_eligible += len(rels)
                enumerated_relpaths |= rels
                violations += vs
                continue
            if entry.is_symlink():
                raise GateInputError(f"{entry.path}: symlinks are refused")
            if entry.is_dir(follow_symlinks=False):
                if entry.name == "__pycache__" or entry.name.startswith("."):
                    # A dot-*directory* (never a dot-*file* -- those fall through to
                    # the `is_file` branch below, matching `_root_level_files`'s own
                    # inclusion of dot-files), pruned identically to
                    # `_discover_modules`'s top-level exclusion. ADR-011 D8: counted
                    # under its own reason (GATE2-R1-F12-D8-FILE-COUNTS-2026-10-05) --
                    # the two reasons are disjoint, since `__pycache__` does not start
                    # with a dot, and their sum is the unchanged D5.5 aggregate.
                    if entry.name == "__pycache__":
                        counts.pruned_pycache += 1
                    else:
                        counts.pruned_dot += 1
                    continue
                # Not discovered, not `_shared`, not pruned: a namespace candidate
                # (ADR-011 D5.2) -- the directory `_discover_modules` silently
                # dropped because it has no `__init__.py`.
                # R1-F12 / ADR-011 D8
                # (GATE2-R1-F12-D8-NAMESPACE-FILE-PRUNE-COUNTS-2026-10-06): counted as
                # probed BEFORE the probe runs, so a probe that aborts mid-traversal is
                # still disclosed as attempted rather than vanishing with the frame, and
                # `counts` is handed in as the probe's file/prune sink. Neither changes
                # any bucketing, violation or return value here.
                counts.namespace_probes += 1
                inert_count, offender = _scan_namespace_subtree(Path(entry.path), counts)
                if offender is not None:
                    # ADR-011 D8: the probe stopped at its first non-inert file, so its
                    # figures for this directory are observations up to that point.
                    counts.namespace_probe_short_circuited += 1
                    relpath = offender.relative_to(modules_dir).as_posix()
                    violations.append(Violation(
                        "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH", relpath,
                        f"non-discovered directory {entry.name!r} under --modules-dir "
                        "has no manifest-declared owner and contains a non-inert file "
                        "(ADR-011 D5.2) -- since PEP 420 this is a fully importable "
                        "namespace package with no declared ownership",
                    ))
                else:
                    counts.namespace_inert += inert_count
                continue
            if entry.is_file(follow_symlinks=False):
                counts.root_files += 1
                # A modules-root file is its own eligible bucket (ADR-011 D4/D5.1):
                # `scan_units` walks these as the `_root` importer, so the reverse
                # diff must be able to account for them. `entry.name` is already the
                # modules-dir-relative path for a direct child.
                enumerated_relpaths.add(entry.name)
                continue
            raise GateInputError(f"{entry.path}: not a regular file")
    except GateInputError as exc:
        # ADR-011 D5.5/D8: whatever this pass had already established stays on
        # the face of the ERROR report the caller builds from this exception,
        # labelled as a lower bound. Re-raised unchanged otherwise -- the run
        # still fails closed at ERROR exit 2 (D7), and the reverse diff and
        # dedupe below deliberately do not run on a partial enumeration.
        exc.notes = partial_notes()
        raise
    # ADR-011 D5.1, reverse direction: every path the per-module/`_shared`/root
    # walks actually reached must also be accounted for by this second,
    # independent enumeration. A walked path the enumeration does not find
    # eligible in any bucket is unattributed -- it means the two traversals
    # disagree about what is in the tree (a walk that reached a path the
    # independent enumeration prunes, refuses or never sees), and a
    # reconciliation that only checked the other direction would accept the
    # walk's own say-so for exactly the paths it then goes on to scan.
    for relpath in sorted(walked_relpaths - enumerated_relpaths):
        violations.append(Violation(
            "MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH", relpath,
            "the module walk reached a path the independent coverage "
            "enumeration does not find eligible under any discovered module, "
            "_shared, or the modules root (ADR-011 D5.1 reverse coverage "
            "reconciliation) -- the two traversals disagree about this path, "
            "reported here instead of trusting the walk that produced it",
        ))
    violations = _dedupe_coverage_violations(violations)
    return violations, _coverage_notes(counts, len(violations), partial=False)


def _file_package_info(rel_path: Path, modules_root: str) -> str:
    """The dotted `__package__` a relative import inside this file resolves against."""
    parts = rel_path.with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
        return modules_root + ("." + ".".join(parts) if parts else "")
    return modules_root + ("." + ".".join(parts[:-1]) if parts[:-1] else "")


def _resolve_relative(package: str, level: int, name: str | None) -> str | None:
    """importlib._bootstrap._resolve_name's own algorithm: `None` means the
    relative import escapes beyond the root package."""
    bits = package.rsplit(".", level - 1)
    if len(bits) < level:
        return None
    base = bits[0]
    return f"{base}.{name}" if name else base


def _import_targets(node: ast.AST, package: str, relpath: str) -> list[tuple[str, int]]:
    """Resolve one `Import`/`ImportFrom` node to its absolute dotted path(s)."""
    if isinstance(node, ast.Import):
        return [(alias.name, node.lineno) for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        if node.level == 0:
            return [(node.module, node.lineno)] if node.module else []
        resolved = _resolve_relative(package, node.level, node.module)
        if resolved is None:
            raise GateInputError(
                f"{relpath}:{node.lineno}: relative import (level {node.level}) escapes "
                f"beyond package {package!r}"
            )
        return [(resolved, node.lineno)]
    return []


# Rule 6 pre-lexer trigger (GATE2-R1-D1A-STABILIZATION-2026-10-05, widened by
# ADR-011 D6.1 at GATE2-R1-D6-TRIGGER-I1-2026-10-05): a regex "SQL-ish" classifier,
# not a parser. D6.1 makes the full `_TRIGGER_VERBS` set (defined above) the trigger
# on its own -- a table-position clause keyword is no longer required to treat text
# as SQL-ish at all. This is a deliberate widening, not a loosening: D6.1 is a broad
# *over*-approximation, so triggering on more text can only ever add ERRORs via the
# D6.3 backstop below, never create a silent PASS. `_TABLE_KEYWORD_RE` remains the
# minimal keyword set the identifier lexer below uses for extraction. Widening
# extraction to cover every list position for every keyword is still largely
# unimplemented SQL-lexer work (ADR-011 D6/D6.7); the exception is the bounded
# comma-continuation subcase implemented by the single shared list walker
# `_table_list_positions` below -- including both alias forms (bare and `AS`) --
# which every `_LIST_POSITION_SIGNALS` signal goes through: `FROM`, `JOIN` and the
# context-sensitive table-position `USING`
# (GATE2-R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-JOIN-USING, extending
# GATE2-R04-GATE2-R2-N01-D67-EXPLICIT-POSITION-RESULT-CORE-ALIAS-LISTS from the
# `FROM`-only walk it originally implemented). D6.7's per-position accounting seam
# itself is `_table_position_results`. `ONLY` is a modifier consumed inside that same
# walk's target lexing, not a signal of its own
# (GATE2-R2-N01-D67-ONLY-MODIFIER-SHARED-TARGET-WALK-2026-10-06). The bare-verb
# `TRUNCATE` family joined that same walk via its own context-sensitive signal
# source (GATE2-R2-N01-D67-TRUNCATE-BARE-VERB-SIGNAL-2026-10-06); `COPY` joined it
# next, also via its own context-sensitive signal source
# (GATE2-R2-N01-D67-COPY-DIRECTION-QUALIFIED-DECISION-2026-10-06); and the last
# D6.7.3 form, `GRANT`/`REVOKE ... ON`, joined it the same way
# (GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06) -- again one context-sensitive
# signal source plus `_LIST_POSITION_SIGNALS` membership, no second list walk.
_TABLE_KEYWORD_RE = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\b", re.IGNORECASE)
_TRIGGER_VERB_RE = re.compile(
    r"\b(?:" + "|".join(sorted(_TRIGGER_VERBS)) + r")\b", re.IGNORECASE
)
# ADR-011 D6.3: the backstop's own table-position-keyword check is deliberately the
# full `_TABLE_POSITION_KEYWORDS` set (a superset of `_TABLE_KEYWORD_RE` -- it also
# carries ONLY and REFERENCES), independent of what the extractor above can actually
# resolve into an identifier: a keyword the extractor cannot yet resolve must still
# fail closed via the backstop below, never pass silently.
_TABLE_POSITION_KEYWORD_RE = re.compile(
    r"\b(?:" + "|".join(sorted(_TABLE_POSITION_KEYWORDS)) + r")\b", re.IGNORECASE
)
# A combined `_BARE_VERB_FORMS` regex (`TRUNCATE|COPY`) previously lived here and
# fed `_has_bare_table_verb_form` directly. GATE2-R2-N01-D67-COPY-DIRECTION-
# QUALIFIED-DECISION-2026-10-06 §4.1 item 5 made `COPY` context-sensitive there
# (it must fire only when at least one occurrence is a table-target form, never
# unconditionally on the bare keyword), which `TRUNCATE` and `COPY` can no longer
# share one regex to decide -- `_has_bare_table_verb_form` below now checks
# `_TRUNCATE_KEYWORD_RE` (defined with the rest of the `TRUNCATE` bare-verb
# signal source below) and `_COPY_KEYWORD_RE`/`_copy_table_position_matches`
# (same, for `COPY`) independently instead.
# ADR-011 D6.3: "GRANT ... ON" is the one bare-table verb form with no keyword of
# its own ("ON" is deliberately excluded from `_TABLE_POSITION_KEYWORDS` generically
# -- a `JOIN ... ON` condition is not a table position -- so it needs its own check
# here, scoped to a GRANT/REVOKE statement specifically). These same two regexes
# back the family's own context-sensitive signal source below
# (`_grant_revoke_on_table_position_matches`, GATE2-R2-N01-D67-GRANT-REVOKE-ON-
# 2026-10-06), so the backstop's notion of "this text has a GRANT/REVOKE ... ON"
# and the extractor's cannot drift onto different keyword spellings.
_GRANT_REVOKE_RE = re.compile(r"\b(?:GRANT|REVOKE)\b", re.IGNORECASE)
_ON_KEYWORD_RE = re.compile(r"\bON\b", re.IGNORECASE)


def _is_sql_ish(text: str) -> bool:
    return bool(_TRIGGER_VERB_RE.search(text))


def _has_bare_table_verb_form(text: str) -> bool:
    """ADR-011 D6.3: a bare-table verb form is present when the table name would
    follow the verb directly with no table-position keyword in between --
    `TRUNCATE`/`COPY` (`_BARE_VERB_FORMS`), or a GRANT/REVOKE statement's
    table-level `ON` clause. `LOCK TABLE`/`DROP TABLE`/`ALTER TABLE`/`CREATE TABLE`
    already carry the literal `TABLE` keyword, so `_TABLE_POSITION_KEYWORD_RE`
    covers those without any extra check here.

    `TRUNCATE` is unconditional, as before: any occurrence is a bare-table verb
    form. `COPY` is context-sensitive (qualified COPY decision §2/§4.1,
    GATE2-R2-N01-D67-COPY-DIRECTION-QUALIFIED-DECISION-2026-10-06 §2/§4.1 item
    5): it fires iff at least one `COPY` occurrence in `text` is a
    *table-target* form -- the exact same structural question
    `_copy_table_position_matches` below already decides for the signal
    stream, asked here rather than re-implemented, so the two can never drift
    onto different answers for the same text. A `COPY` all of whose
    occurrences are well-formed, balanced query forms
    (`COPY (SELECT 1) TO STDOUT`) carries no table position at all and must
    NOT fire this backstop -- D6.3 clause 3's pre-existing zero-table clean
    class, reached for `COPY` for the first time by this branch.

    GRANT/REVOKE ... ON is deliberately left UNCONDITIONAL by
    GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06, even though that family now
    has a signal source of its own (unlike `COPY`, whose branch above is
    context-sensitive by the qualified decision's own §4.1 item 5). Making it
    context-sensitive here would reclassify every GRANT/REVOKE `ON` form the
    new source deliberately does not claim -- `ON SCHEMA`, `ON SEQUENCE`,
    `ON ALL TABLES IN SCHEMA`, `ON DATABASE` -- from today's fail-closed I-1
    ERROR to a clean zero-table PASS. That is a D6.3 clause-3 reclassification,
    which `COPY`'s equivalent needed its own qualified decision record to
    authorize; this increment has none for these forms, so it removes no ERROR
    surface and every form its source excludes keeps exactly the refusal it
    had."""
    if _TRUNCATE_KEYWORD_RE.search(text):
        return True
    if _COPY_KEYWORD_RE.search(text) and any(
            True for _ in _copy_table_position_matches(text)):
        return True
    return bool(_GRANT_REVOKE_RE.search(text) and _ON_KEYWORD_RE.search(text))


def _implies_table_position(text: str) -> bool:
    """Whether this text carries a table position at all -- a table-position
    keyword (the broader ONLY/REFERENCES-inclusive `_TABLE_POSITION_KEYWORDS`,
    not just what `_TABLE_KEYWORD_RE` extraction can resolve) or a bare-table
    verb form.

    Extracted verbatim from `_scan_sql_text`'s D6.3 I-1 backstop condition by
    GATE2-R1-F06-INTERPOLATED-VERB-FSTRING-2026-10-05 so that backstop and the
    f-string branch in `_uninspectable_for_node` cannot drift apart: both ask
    the same ADR-011 D6.3 question, and a keyword added to
    `_TABLE_POSITION_KEYWORDS` must widen both at once. Behaviour at the
    original call site is unchanged -- this is the same disjunction, named.

    Note this is deliberately independent of `_is_sql_ish`: a table position
    can be present with no trigger verb anywhere in the text, which is exactly
    the condition the interpolated-verb f-string branch keys on."""
    return bool(_TABLE_POSITION_KEYWORD_RE.search(text) or _has_bare_table_verb_form(text))


# --- GATE2-R1-D1A-QUOTED-LEXER-2026-10-05: explicit table-identifier lexer -------
#
# Replaces the prior `_TABLE_IDENT_RE` regex, which could not capture a
# double-quoted identifier at all (every quote character fell outside its
# `[A-Za-z_][A-Za-z0-9_]*` character class) and silently truncated a 3+-part
# dotted name to its first two parts. A regex alternation of the shape
# `"[^"]*"` was deliberately rejected for the quoted-segment case: it treats
# the *first* unescaped `"` as the closing quote, so an escaped embedded quote
# (SQL's `""`, one literal `"` inside the identifier) would make the regex
# stop early and read the remainder of the real identifier as trailing text --
# a partial capture that could misattribute the identifier rather than fail
# closed. The scanner below walks the text character-by-character instead, so
# an identifier is captured in full, exactly as written (quotes preserved), or
# not captured at all -- it never stops partway through one.
_BARE_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_KEYWORD_WHITESPACE_RE = re.compile(r"\s+")


def _lex_quoted_segment(text: str, pos: int) -> tuple[str, int] | None:
    """Scans one PostgreSQL double-quoted identifier segment starting at
    `text[pos]` (which must be `"`). A `""` pair found while scanning is an
    escaped literal `"` character inside the segment, not a closing quote --
    the segment only closes on a `"` that is NOT immediately followed by a
    second `"`. Returns `(raw_segment_with_quotes, end_pos)` with the quotes
    still attached, or `None` if the text ends before the segment closes
    (an unterminated quote is a lex failure, never the unterminated prefix)."""
    assert text[pos] == '"'
    i = pos + 1
    n = len(text)
    while i < n:
        if text[i] == '"':
            if i + 1 < n and text[i + 1] == '"':
                i += 2
                continue
            return text[pos:i + 1], i + 1
        i += 1
    return None


def _lex_identifier_segment(text: str, pos: int) -> tuple[str, int] | None:
    """One identifier segment -- quoted or bare -- starting exactly at
    `text[pos]`. Returns `(raw_segment, end_pos)` or `None` if neither shape
    matches at `pos` at all (including an unterminated quote; see
    `_lex_quoted_segment`)."""
    if pos >= len(text):
        return None
    if text[pos] == '"':
        return _lex_quoted_segment(text, pos)
    m = _BARE_IDENT_RE.match(text, pos)
    if m is None:
        return None
    return m.group(0), m.end()


def _lex_dotted_identifier(text: str, pos: int) -> tuple[str, int] | None:
    """The full table-position identifier starting exactly at `text[pos]`:
    one or more identifier segments -- quoted or bare, in any mix -- joined
    by `.`, with every quote character preserved exactly as written. Returns
    `(raw_identifier_text, end_pos)`, or `None` if no identifier segment
    starts at `pos` at all (this is the only failure `_dangling_keywords`
    below treats as "no identifier follows the keyword"). A `.` not followed
    by a well-formed segment simply ends the identifier at the segment
    before it -- mirroring the prior regex's optional second part -- rather
    than failing the whole lex, so this only ever extends what has already
    been successfully captured; it never discards it."""
    first = _lex_identifier_segment(text, pos)
    if first is None:
        return None
    raw, end = first
    while end < len(text) and text[end] == ".":
        nxt = _lex_identifier_segment(text, end + 1)
        if nxt is None:
            break
        nxt_raw, end = nxt
        raw = f"{raw}.{nxt_raw}"
    return raw, end


def _identifier_after_keyword(text: str, keyword_end: int) -> tuple[str, int] | None:
    """The identifier immediately following a table-position keyword match
    ending at `keyword_end`, requiring at least one whitespace character in
    between (mirroring the prior regex's `\\s+` so a keyword glued directly
    to the next token still correctly fails to match). Returns `(raw_identifier,
    end_pos)` or `None`."""
    ws = _KEYWORD_WHITESPACE_RE.match(text, keyword_end)
    if ws is None:
        return None
    return _lex_dotted_identifier(text, ws.end())


# ADR-011 addendum D6.7: a `,` continuation at the same lexical level, used to
# extend a table-list position across its comma-separated elements. This regex is
# the continuation itself; `_skip_list_element_alias` below is what lets the walk
# reach a continuation that sits behind a list element's alias. Both are shared by
# every `_LIST_POSITION_SIGNALS` signal through `_table_list_positions` -- including
# the bare-verb `TRUNCATE` family as of
# GATE2-R2-N01-D67-TRUNCATE-BARE-VERB-SIGNAL-2026-10-06, the bare-verb `COPY`
# family as of GATE2-R2-N01-D67-COPY-DIRECTION-QUALIFIED-DECISION-2026-10-06, and
# the `GRANT`/`REVOKE ... ON` object list as of
# GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06, which was the last bare-verb family
# with no position result to continue from.
_LIST_ITEM_CONTINUATION_RE = re.compile(r"\s*,\s*")
# A list element's `AS` alias introducer. Required to be preceded by at least
# one whitespace character for the same reason `_identifier_after_keyword` is
# (`mem_tAS x` is one identifier, not an aliased one), and `\b`-terminated so
# an identifier merely *starting* with `as` (`FROM mem_t assets_view, x`) is
# not mistaken for the keyword.
_ALIAS_AS_RE = re.compile(r"\s+AS\b", re.IGNORECASE)
# ADR-011 addendum D6.7.3: PostgreSQL's optional `ONLY` inheritance modifier,
# which sits between a table target's introducing signal (or its `,` list
# continuation) and the target's own identifier -- `FROM ONLY mem_roster`,
# `FROM mem_roster, ONLY mem_events`. `\b`-terminated so an identifier merely
# *starting* with `only` (`FROM only_members`) is not mistaken for the keyword;
# matched at the target's own start offset (never searched for), so an `ONLY`
# anywhere else in the statement cannot be consumed as a modifier here.
#
# This is deliberately NOT a `_TABLE_POSITION_SIGNAL_SOURCES` entry: `ONLY`
# introduces no table position of its own, it modifies one another signal
# already introduced (GATE2-R2-N01-D67-ONLY-BARE-SIGNAL-ROOT-CAUSE-2026-10-06
# §"Structural seam"). Treating it as an independent signal would double-count
# the target it modifies; leaving it unconsumed -- the pre-increment state --
# made `ONLY` itself the extracted identifier, so `FROM ONLY mem_roster`
# reached state 6 ERROR `MODULE_DEPS_TABLE_UNATTRIBUTED` naming the modifier
# while its one genuinely-owned target went unexamined, and
# `FROM mem_roster, ONLY bil_invoices` reported the same misattribution in
# place of the cross-domain FAIL the billing target earns. It remains a
# `_TABLE_POSITION_KEYWORDS` member (D6.7.4's vocabulary floor), so a bare
# `ONLY` in text carrying no recognised signal still fails closed through the
# D6.3 I-1 backstop exactly as before -- consuming the modifier here removes no
# ERROR surface.
_ONLY_MODIFIER_RE = re.compile(r"ONLY\b", re.IGNORECASE)


@dataclass(frozen=True)
class _TablePositionResult:
    """ADR-011 D6.7.2 (GATE2-R04-GATE2-R2-N01-D67-EXPLICIT-POSITION-RESULT-CORE-
    ALIAS-LISTS): one recognised table position's own accounting record.

    This type *is* the seam D6.7.2 requires, and it replaces the aggregate one
    the round-2 P0 was found in. Extraction previously returned a `list[str]`
    of whatever identifiers happened to lex plus a single statement-wide
    dangling boolean; neither carried any record of *which* recognised position
    each outcome belonged to, so the scanner could only ever ask the aggregate
    question `if not idents:` -- and that question is answered "there is at
    least one identifier, so nothing is unaccounted" by a statement in which
    one position lexed cleanly and another was never resolved at all. That is
    the documented false-clean shape (`GATE2-R2-N01-D67-POSITION-ACCOUNTING-
    ROOT-CAUSE-2026-10-06.md`): `SELECT a FROM mem_roster m, bil_invoices b`
    reached PASS exit 0 while asserting its counts were complete.

    One record is emitted per recognised table position, resolved or not, so
    the accounting comparison D6.7.2 mandates is structural rather than
    numeric: every position carries either an `identifier` for D3.2
    attribution or an `unresolved` reason, never neither and never both. A
    position cannot be dropped from the stream without deleting its record,
    and a reader of the refusal can be told which signal, at which offset,
    went unaccounted.

    `signal`/`signal_start` name the signal keyword as written and where it
    was found; `element_start` is where this particular position's own text
    begins (for a comma continuation that is the element after the `,`, not
    the keyword), so two positions introduced by the same keyword are still
    told apart in a refusal."""
    signal: str
    signal_start: int
    element_start: int
    identifier: str | None
    unresolved: str | None

    def __post_init__(self) -> None:
        # Fail closed on the either/or invariant rather than trusting every
        # construction site to honour it: a record with neither field set
        # would be a position that is silently neither attributed nor refused
        # -- precisely the accounting hole this type exists to make
        # impossible -- and one with both set would let a caller reading only
        # `identifier` attribute a position its own record calls unresolved.
        if (self.identifier is None) == (self.unresolved is None):
            raise ValueError(
                f"ADR-011 D6.7.2: table position {self.signal!r} at offset "
                f"{self.signal_start} must carry exactly one of an identifier "
                f"or an unresolved reason, got identifier={self.identifier!r} "
                f"unresolved={self.unresolved!r}"
            )

    def describe(self) -> str:
        """This position named for a D6.7.2 refusal -- which signal, where, and
        why it did not resolve."""
        return (f"{self.signal.upper()} signal at offset {self.signal_start}, "
                f"position at offset {self.element_start}: {self.unresolved}")


_NO_IDENTIFIER_AFTER_KEYWORD = (
    "not followed by an identifier (the table name is concatenated in)"
)
_NO_IDENTIFIER_AFTER_COMMA = (
    "a ',' list continuation is not followed by an identifier"
)
# ADR-011 D6.7.2: a dangling `FROM ONLY` is still exactly one unresolved
# position, but neither reason above describes it truthfully -- nothing is
# concatenated in and no `,` is involved; the modifier's target is simply
# absent. A refusal that misnames why a position went unaccounted is not
# actionable, so the modifier case carries its own reason.
_NO_IDENTIFIER_AFTER_ONLY = (
    "an 'ONLY' modifier is not followed by a table identifier"
)


def _element_start_after_keyword(text: str, keyword_end: int) -> int:
    """Where the position's own text begins after a signal keyword ending at
    `keyword_end` -- i.e. past `_identifier_after_keyword`'s required
    whitespace. Reported for diagnosis only; when no whitespace follows at all
    (the glued `FROM`/`FROMx` case that correctly fails to resolve) the
    keyword's own end is the honest offset to name."""
    ws = _KEYWORD_WHITESPACE_RE.match(text, keyword_end)
    return ws.end() if ws is not None else keyword_end


def _skip_list_element_alias(text: str, pos: int) -> int | None:
    """The offset just past a table-list element's alias starting at `pos`
    (immediately after the element's identifier), or `None` if no alias is
    there.

    Both PostgreSQL alias forms are covered: `AS <alias>` and the bare
    `<alias>`. This is deliberately only a *skip* -- an alias is never
    extracted as an identifier and never becomes a table position of its own
    (it names no table), so this function's single purpose is to let
    `_table_list_positions` reach a `,` continuation that an alias sits in
    front of. Before this, the continuation walk looked for the `,`
    immediately after the element identifier, so `FROM mem_roster m,
    bil_invoices b` ended the walk at `mem_roster` and the second position was
    never recognised at all -- the N8/N9 false clean.

    `None` here does not mean "unresolved position": it means the walk simply
    continues from the element identifier, which is the correct reading of an
    unaliased element. Whether the skip is *taken* is decided by the caller,
    which only accepts it when a `,` genuinely follows -- so an ordinary
    trailing clause (`FROM mem_t GROUP BY a, b`) cannot be read as an aliased
    list, even though its first word lexes like an alias."""
    as_kw = _ALIAS_AS_RE.match(text, pos)
    if as_kw is not None:
        aliased = _identifier_after_keyword(text, as_kw.end())
        return None if aliased is None else aliased[1]
    ws = _KEYWORD_WHITESPACE_RE.match(text, pos)
    if ws is None:
        return None
    bare = _lex_dotted_identifier(text, ws.end())
    return None if bare is None else bare[1]


def _consume_only_modifier(text: str, pos: int) -> int:
    """The offset of a table target's own identifier, given the offset `pos` at
    which the target's text begins -- i.e. past an `ONLY` inheritance modifier
    when one is written there, and `pos` itself when one is not.

    The modifier is consumed unconditionally once matched, including when no
    identifier follows it at all (`FROM ONLY`, `FROM ONLY;`): returning `pos` in
    that case would put `ONLY` back in front of the lexer and resolve the
    position to the modifier's own text, which is the misattribution this
    function exists to remove. Consuming it instead leaves the target
    unresolved, so the position is refused by `_table_list_positions` below
    rather than attributed -- D6.7.1's safe direction."""
    kw = _ONLY_MODIFIER_RE.match(text, pos)
    if kw is None:
        return pos
    ws = _KEYWORD_WHITESPACE_RE.match(text, kw.end())
    return ws.end() if ws is not None else kw.end()


def _lex_target_identifier(text: str, pos: int) -> tuple[str, int] | None:
    """One table target starting exactly at `text[pos]`: the optional `ONLY`
    modifier, then the identifier itself. `(raw_identifier, end_pos)` or `None`
    on the same terms as `_lex_dotted_identifier`, which does the lexing -- the
    modifier only moves where it starts.

    This and `_target_identifier_after_keyword` below are the *one* place the
    modifier is consumed, reached by both of `_table_list_positions`' element
    sites (first element and `,` continuation), so a target cannot accept the
    modifier in one list element and reject it in the next."""
    return _lex_dotted_identifier(text, _consume_only_modifier(text, pos))


def _target_identifier_after_keyword(
    text: str, keyword_end: int
) -> tuple[str, int] | None:
    """`_identifier_after_keyword` for a *table target* rather than a bare
    identifier: the same required whitespace after a signal keyword ending at
    `keyword_end`, then `_lex_target_identifier`'s optional `ONLY` modifier and
    identifier.

    Kept distinct from `_identifier_after_keyword` itself because that function
    is also how `_skip_list_element_alias` reads an `AS` alias, and an alias is
    not a table target -- no modifier may be consumed there."""
    ws = _KEYWORD_WHITESPACE_RE.match(text, keyword_end)
    if ws is None:
        return None
    return _lex_target_identifier(text, ws.end())


def _unresolved_target_reason(text: str, pos: int, fallback: str) -> str:
    """Why no identifier could be lexed for the table target starting at `pos`
    -- the `ONLY` reason when the modifier was consumed there, `fallback`
    otherwise."""
    return (_NO_IDENTIFIER_AFTER_ONLY if _ONLY_MODIFIER_RE.match(text, pos)
            else fallback)


def _table_list_positions(text: str, keyword: re.Match[str]) -> list[_TablePositionResult]:
    """ADR-011 D6.7.1/D6.7.2/D6.7.3: every table position introduced by one
    list-bearing signal match, as its own `_TablePositionResult`.

    This is the **one** shared list-walk mechanism, used by every
    `_LIST_POSITION_SIGNALS` signal (`FROM`, `JOIN`, and the context-sensitive
    table-position `USING`) rather than re-implemented per keyword
    (GATE2-R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-JOIN-USING). It is deliberately
    written against `keyword` alone and knows nothing about *which* signal it is
    walking: the grammar of a same-depth comma list does not vary by introducing
    keyword, so a hand-duplicated per-keyword copy could only ever drift from the
    others -- which is the shape ADR-011's Alternatives table rejects as the
    keyword treadmill, and the shape in which `JOIN mem_events, bil_invoices`
    and `USING mem_events, bil_invoices` both reached PASS exit 0 while the
    `FROM` form of the same list was already refused.

    The first element mirrors `_identifier_after_keyword`'s
    whitespace-then-identifier contract, so a bare `FROM` with no identifier
    after it yields one *unresolved* position rather than nothing at all. The
    walk then continues across `,`-separated elements at the same lexical
    level, stepping over each element's alias (bare or `AS`,
    `_skip_list_element_alias`) so an aliased list reaches every element and
    not merely the first -- the exact partial-extraction shape ADR-011 D6.7
    identifies as strictly less safe than extracting none.

    An alias skip is only accepted when a `,` actually follows it. That is
    what keeps the walk from reading an ordinary trailing clause as a list
    continuation: in `SELECT a FROM mem_t GROUP BY x, y` the word `GROUP`
    lexes like a bare alias, but no `,` follows it, so the skip is discarded
    and the walk ends at `mem_t` -- while in `FROM mem_roster m, bil_invoices`
    the `,` is there and the second position is recognised. The alias skip is
    therefore never able to swallow a table position: consuming a keyword as
    an alias (`FROM mem_t JOIN ...`, `DELETE FROM mem_t USING ...`) cannot
    hide that keyword's own position, because every signal source below scans
    the full statement text independently of this walk.

    A `,` with no well-formed identifier after it yields an unresolved
    position, never a silently shortened list -- D6.7.3's "an element the
    lexer cannot reduce to an identifier is ERROR, never dropped". Note this
    also makes a `FROM`-list element that is a parenthesised subquery
    (`FROM mem_t t, (SELECT ...) s`) an unresolved position at exit 2 rather
    than a silently dropped one, which is D6.7.1's stated safe direction.

    Every element -- the first and every `,` continuation alike -- is read as a
    table *target* rather than a bare identifier
    (GATE2-R2-N01-D67-ONLY-MODIFIER-SHARED-TARGET-WALK-2026-10-06), so an
    `ONLY` inheritance modifier in front of it is consumed by the one
    `_lex_target_identifier` seam both sites go through and the position
    resolves to the table it modifies. `ONLY` is therefore never a position of
    its own and never an extracted identifier: `FROM ONLY mem_roster` is the one
    owned position it says it is, and `FROM mem_roster, ONLY bil_invoices` is
    two positions, the second of them the billing target that earns the
    cross-domain FAIL -- where both previously resolved to the modifier itself
    and ERRORed at state 6 naming `ONLY`. A modifier with no target after it
    (`FROM ONLY`) stays exactly one *unresolved* position, carrying its own
    reason, rather than resolving to the modifier's text.

    Scope: the signals in `_LIST_POSITION_SIGNALS`, which as of
    GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06 covers `FROM`, `JOIN`, `USING`,
    `INTO`, `TABLE`, `UPDATE`, `REFERENCES`, the bare-verb `TRUNCATE` and `COPY`,
    and the `GRANT`/`REVOKE` object-clause `ON`. Adding each of them was a
    membership change to that frozenset and nothing else -- no copy of this walk --
    which is the point of routing every list signal through here. `TRUNCATE`,
    `COPY` and `ON` additionally each needed their own context-sensitive signal
    source, because unlike the other six they have no table-position keyword of
    their own to be found by (`ON` is a table position only inside a GRANT/REVOKE
    object clause, never in a `JOIN ... ON` condition); once found, each one's list
    is walked here like any other, so `TRUNCATE mem_roster, ONLY bil_invoices`,
    `COPY mem_roster (a, b) FROM STDIN` and `GRANT SELECT ON mem_roster, ONLY
    bil_invoices TO r` all get the comma continuation and the modifier consumption
    for free rather than through a second extractor. D6.7.3's bare-verb forms are
    now all inside this walk's reach."""
    signal = keyword.group()
    first = _target_identifier_after_keyword(text, keyword.end())
    if first is None:
        first_start = _element_start_after_keyword(text, keyword.end())
        return [_TablePositionResult(
            signal, keyword.start(), first_start, None,
            _unresolved_target_reason(text, first_start, _NO_IDENTIFIER_AFTER_KEYWORD),
        )]
    positions = [_TablePositionResult(
        signal, keyword.start(), _element_start_after_keyword(text, keyword.end()),
        first[0], None,
    )]
    pos = first[1]
    while True:
        continuation = _LIST_ITEM_CONTINUATION_RE.match(text, pos)
        if continuation is None:
            after_alias = _skip_list_element_alias(text, pos)
            if after_alias is None:
                break
            continuation = _LIST_ITEM_CONTINUATION_RE.match(text, after_alias)
            if continuation is None:
                break
        element = _lex_target_identifier(text, continuation.end())
        if element is None:
            positions.append(_TablePositionResult(
                signal, keyword.start(), continuation.end(), None,
                _unresolved_target_reason(
                    text, continuation.end(), _NO_IDENTIFIER_AFTER_COMMA),
            ))
            break
        positions.append(_TablePositionResult(
            signal, keyword.start(), continuation.end(), element[0], None,
        ))
        pos = element[1]
    return positions


# ADR-011 D6.7.2 per-table-position signal/identifier accounting seam
# (GATE2-R2-N01-D67-SHARED-SIGNAL-ACCOUNTING-N4), third increment: USING,
# joining REFERENCES (second increment) on one shared seam. REFERENCES is
# already a `_TABLE_POSITION_KEYWORDS` member -- the D6.3 backstop's trigger
# condition already treats a REFERENCES clause as "implies a table
# position" -- but it was invisible to extraction itself, so a statement
# with any other cleanly-extracting table position (e.g. `CREATE TABLE
# mem_t (...)`'s own `TABLE mem_t`) left the REFERENCES target completely
# unexamined: `idents` was non-empty, so neither the per-element loop nor
# the `if not idents:` backstop ever looked at it. The identical shape
# recurs for `DELETE FROM mem_t USING bil_invoices ...`: `FROM mem_t`
# extracts cleanly, so the USING target was silently never examined (the N4
# false-PASS the strategy-reconciliation record names). That is the exact
# partial-extraction-disarms-accounting shape D6.7 identifies: one
# recognised signal's clean extraction must never suppress accounting for
# another.
#
# This is deliberately NOT accomplished by adding REFERENCES/USING to
# `_TABLE_KEYWORD_RE`: that would conflate D6.7.4's vocabulary floor with
# D6.7.2's per-position accounting, which is the one alternative ADR-011
# explicitly rejected ("Widen `_TABLE_KEYWORD_RE` only" -- moves the observed
# instance without touching the class). Nor is USING a context-free signal
# like REFERENCES: `JOIN ... USING (col, col)` is a column list, never a
# table position (the P4 non-vacuity control), so its own signal source
# (`_using_table_position_matches` below) excludes a `USING` immediately
# followed by `(` before it ever reaches either consumer.
#
# REFERENCES and USING are each an independent signal source. Rather than
# giving USING its own hand-duplicated "for kw in ...: found =
# _identifier_after_keyword(...)" copy alongside REFERENCES's (which is
# exactly the keyword-treadmill shape that lets
# `_extract_table_identifiers` and `_dangling_keywords` silently drift onto
# different signal sets -- the root cause the N4 strategy reconciliation
# record named), both are collected into one signal-source tuple that every
# consumer walks identically below. Extraction and dangling-keyword refusal
# are therefore structurally unable to see different signals for the same
# text. A future *signal* increment extends this one tuple, not two
# independently drifting call sites -- but `ONLY` is explicitly not one of
# them: it is a modifier on a target another signal already introduced, so it
# is consumed inside the shared target lexing instead
# (GATE2-R2-N01-D67-ONLY-MODIFIER-SHARED-TARGET-WALK-2026-10-06). Adding it
# here would emit a second position for one target.
#
# GATE2-R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-JOIN-USING (this increment) carries
# that same reasoning one layer up, to the *shape* of a position rather than the
# set of signals: USING's position is a comma list (`DELETE ... USING a, b`), as
# JOIN's is, so USING moves out of the single-identifier tuple and both go through
# the one shared `_table_list_positions` walk via `_LIST_POSITION_SIGNALS` below.
# The two tuples here are therefore the two *shapes* a signal's position can have,
# not two keyword lists to keep in step by hand, and they are consulted through one
# dispatch (`_positions_for_signal`) that every signal in either tuple goes
# through -- so extraction and the dangling-keyword refusal still cannot see
# different signals, and now cannot see different *elements* of the same signal's
# list either.
_REFERENCES_KEYWORD_RE = re.compile(r"\bREFERENCES\b", re.IGNORECASE)
_USING_KEYWORD_RE = re.compile(r"\bUSING\b", re.IGNORECASE)
# ADR-011 D6.7.3's first bare-verb family: `TRUNCATE <table> [, ...]`, where the
# target list follows the verb directly with no table-position keyword in between.
# `TABLE`/`ON` are matched at the verb's own target offset (never searched for), so
# the two contexts below are decided structurally and locally, exactly as
# `_using_table_position_matches` decides USING's.
_TRUNCATE_KEYWORD_RE = re.compile(r"\bTRUNCATE\b", re.IGNORECASE)
_TRUNCATE_TABLE_NOISE_RE = re.compile(r"TABLE\b", re.IGNORECASE)
_TRUNCATE_PRIVILEGE_ON_RE = re.compile(r"ON\b", re.IGNORECASE)


def _truncate_table_position_matches(text: str) -> Iterator[re.Match[str]]:
    """ADR-011 D6.7.2/D6.7.3 context-sensitive `TRUNCATE` signal source -- the
    first of the bare-verb families, which until now yielded no position record
    at all and were refused only by the statement-wide D6.3 I-1 backstop
    (`GATE2-R2-N01-D67-ONLY-BARE-SIGNAL-ROOT-CAUSE-2026-10-06.md` §Reproduction,
    re-executed by this session: `TRUNCATE mem_roster, bil_invoices` produced an
    empty position stream, so the cross-domain target earned
    `MODULE_DEPS_SOURCE_UNINSPECTABLE` rather than the `CROSS_DOMAIN_SQL_IMPORT`
    it names, and an entirely own-module `TRUNCATE mem_roster` was refused as
    uninspectable for a statement whose one target the gate owns).

    Yields only the `TRUNCATE` matches that themselves introduce a table
    position. Two contexts are excluded, each because the position is already
    accounted for elsewhere or is not a table position at all:

      * **`TRUNCATE TABLE ...`** -- the literal `TABLE` keyword is already a
        `_TABLE_KEYWORD_RE` signal and already a `_LIST_POSITION_SIGNALS`
        member, so its comma list is already walked. Yielding here as well would
        emit a *second* stream of positions for the same targets (and the first
        of them would resolve to the word `TABLE` itself -- the same false
        attribution the `ONLY` increment removed). This is the discriminator
        `_BARE_VERB_FORMS`' own comment has always named.
      * **a GRANT/REVOKE privilege name** -- `GRANT TRUNCATE ON mem_t TO r` uses
        `TRUNCATE` as a privilege, not as the statement's verb, and the token
        after it is `ON`. `ON` is reserved in PostgreSQL and so can never be an
        unquoted table name, which is what makes excluding it lossless: a real
        target spelled `"on"` is quoted and still yields. Without this, the
        position would resolve to the identifier `on` and reach D3.2 state 6 --
        ERROR for a table nobody wrote. This source-level exclusion reaches
        `GRANT TRUNCATE ON ...` (TRUNCATE immediately followed by ON) but NOT
        `GRANT TRUNCATE, SELECT ON ...` (TRUNCATE in a comma-separated privilege
        list), which is handled by ADR-011 D6.8's privilege-list suppression at
        the merge point. The two defences are deliberately layered.

        Note this exclusion is *not* a GRANT ... ON signal source: that
        statement's real target is reached by `_grant_revoke_on_table_position_
        matches` (GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06), whose own `ON`
        position is what attributes `GRANT TRUNCATE ON mem_t TO r`'s table --
        this source still yields nothing for it, so the privilege name is still
        never read as the statement's verb.

    A `TRUNCATE` with no whitespace after it at all (end of statement, or
    `GRANT TRUNCATE, SELECT ON ...`) is yielded, not excluded: the shared walk
    then records exactly one *unresolved* position, which is D6.7.1's safe
    direction and keeps the pre-increment ERROR. The list walk itself is not
    this source's concern -- `TRUNCATE` is a `_LIST_POSITION_SIGNALS` member, so
    its comma elements, its `ONLY` modifiers and its unresolvable elements are
    all handled by the one shared `_table_list_positions`."""
    for kw in _TRUNCATE_KEYWORD_RE.finditer(text):
        ws = _KEYWORD_WHITESPACE_RE.match(text, kw.end())
        if ws is not None and (_TRUNCATE_TABLE_NOISE_RE.match(text, ws.end())
                               or _TRUNCATE_PRIVILEGE_ON_RE.match(text, ws.end())):
            continue
        yield kw


# ADR-011 D6.8.1: the compiled keyword pattern whose matches this source yields,
# declared here beside the body that drives it rather than restated in a list next
# to `_TABLE_POSITION_SIGNAL_SOURCES`. `_signal_source_keyword_tokens` reads these
# declarations to derive D6.8.1's suppressible set from the *actual* sources, so a
# keyword added to the pattern flows into that set with no second edit, and a source
# that declares nothing raises at import rather than being silently omitted.
_truncate_table_position_matches.signal_keyword_pattern = (  # type: ignore[attr-defined]
    _TRUNCATE_KEYWORD_RE)


def _using_table_position_matches(text: str) -> Iterator[re.Match[str]]:
    """ADR-011 D6.7.2 context-sensitive USING signal source (third
    increment). Yields only the `USING` matches that introduce a genuine
    table position -- `DELETE ... USING <table> ...` -- never one that opens
    a JOIN column list (`JOIN ... USING (id)`). The two are told apart
    structurally: a `USING` immediately followed, after only whitespace (the
    same contract `_identifier_after_keyword` itself uses), by `(` is a
    column list and is excluded here, before either
    `_extract_table_identifiers` or `_dangling_keywords` ever sees it -- so
    neither consumer needs its own column-list special case.

    Scope: the `DELETE ... USING <table-list>` shape. The column-list
    exclusion above is the whole of this source's context sensitivity; the
    list walk itself is not its concern, because `USING` is a
    `_LIST_POSITION_SIGNALS` member and so its comma elements are walked by
    the shared `_table_list_positions` like any other list signal's
    (GATE2-R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-JOIN-USING). A
    USING-introduced subquery element is an unresolved position at exit 2
    rather than a dropped one, per D6.7.1's safe direction."""
    for kw in _USING_KEYWORD_RE.finditer(text):
        ws = _KEYWORD_WHITESPACE_RE.match(text, kw.end())
        after = ws.end() if ws is not None else kw.end()
        if after < len(text) and text[after] == "(":
            continue
        yield kw


# ADR-011 D6.8.1, as above: this source's keyword pattern, declared at its own body.
_using_table_position_matches.signal_keyword_pattern = (  # type: ignore[attr-defined]
    _USING_KEYWORD_RE)


# ADR-011 D6.7.3's second bare-verb family, decided by
# GATE2-R2-N01-D67-COPY-DIRECTION-QUALIFIED-DECISION-2026-10-06:
# `COPY table_name [(cols)] FROM|TO {STDIN|STDOUT|PROGRAM '...'|'<path>'}`. As
# with `TRUNCATE`, the target follows the verb directly with no table-position
# keyword in front of it, so `COPY` needs its own context-sensitive signal
# source rather than being found by `_TABLE_KEYWORD_RE`. Unlike `TRUNCATE`,
# `COPY` also has a second, genuinely table-free form -- the query form,
# `COPY (SELECT ...) TO STDOUT` -- and a top-level direction keyword
# (`FROM`/`TO`) immediately after a table-target `COPY`'s target (and optional
# column list) that is not itself a table position at all (decision record
# §1.2: the direction token is not a member of the true table-position set).
# `_COPY_WS_RE` is the permissive (zero-or-more) whitespace match the column-
# list/direction lookahead below needs -- deliberately more permissive than
# `_KEYWORD_WHITESPACE_RE`'s required `\s+`, since D6.7.1's safe direction is
# to keep *looking* for the column list/direction rather than giving up for
# want of a space, and failing to find one there only ever falls back to
# retaining the `FROM` as a position (never to a false exclusion).
_COPY_KEYWORD_RE = re.compile(r"\bCOPY\b", re.IGNORECASE)
_COPY_WS_RE = re.compile(r"\s*")
_COPY_DIRECTION_FROM_RE = re.compile(r"FROM\b", re.IGNORECASE)


def _copy_table_position_matches(text: str) -> Iterator[re.Match[str]]:
    """ADR-011 D6.7.2/D6.7.3 and qualified decision §4.1 `COPY` signal source,
    modelled on `_truncate_table_position_matches` above -- the second
    bare-verb family, which until now yielded no position record at all and
    was refused only by the statement-wide D6.3 I-1 backstop.

    Yields only the `COPY` matches whose target offset is a **table-target**
    form: the first non-whitespace character at the target offset is not
    `(`. `COPY (SELECT ...) TO STDOUT`'s query form is therefore never
    yielded here -- its own target carries no table position at all (the
    decision record's §2 D6.3 clean zero-table reclassification, decided by
    `_has_bare_table_verb_form` above, which asks this same question); its
    inner `FROM`/`JOIN`/etc, if any, are independent
    `_TABLE_POSITION_SIGNAL_SOURCES` positions and untouched by this source.

    A `COPY` whose target is absent, unlexable, or opens an unbalanced/
    unterminated `(` is yielded, never excluded -- D6.7.1's safe direction:
    `COPY` is a `_LIST_POSITION_SIGNALS` member (see below), so the shared
    `_table_list_positions` walk then records exactly one *unresolved*
    position for it, which is what keeps a bare, dangling `COPY` and an
    unterminated `COPY (SELECT 1` both at ERROR
    `MODULE_DEPS_SOURCE_UNINSPECTABLE`, unchanged from before this
    increment."""
    for kw in _COPY_KEYWORD_RE.finditer(text):
        target_offset = _element_start_after_keyword(text, kw.end())
        if (target_offset < len(text) and text[target_offset] == "("
                and _skip_balanced_parens(text, target_offset) is not None):
            continue
        yield kw


# ADR-011 D6.8.1, as above: this source's keyword pattern, declared at its own body.
_copy_table_position_matches.signal_keyword_pattern = (  # type: ignore[attr-defined]
    _COPY_KEYWORD_RE)


def _copy_direction_exclusion_offset(text: str, kw: re.Match[str]) -> int | None:
    """Qualified COPY decision §4.1: the offset of a table-target `COPY` match `kw`'s
    own top-level direction `FROM`, if one is *positively computed* for it --
    otherwise `None`. This is the predicate `_table_keyword_position_matches`
    below filters `_TABLE_KEYWORD_RE`'s own `FROM` matches against: it is an
    offset-equality check, never a pattern match against `STDIN`/`STDOUT`/
    `PROGRAM`/a path token, per the decision record's §4.1 item 4.

    Mirrors the shared target walk exactly (`_lex_target_identifier`, the same
    `ONLY`-modifier-then-identifier seam `_table_list_positions` uses), then
    looks past one optional, balanced parenthesised column list
    (`_skip_balanced_parens`, the same helper `_collect_cte_names` already
    uses elsewhere in this module -- no second balanced-paren implementation)
    for a literal `FROM` immediately after.

    Returns `None` -- no exclusion applies, D6.7.1's safe direction, `FROM`
    stays a position -- for every case the direction offset cannot be
    positively computed: no target offset at all (end of text), a query-form
    target (`(` at the target offset; the query form yields no exclusion
    offset at all per decision-record §1.6(a)), a target that does not lex as
    an identifier, an unbalanced/unterminated column list, or no literal
    `FROM` immediately after the target/column list (including `TO`, which
    needs no exclusion of its own since `TO` is not in `_TABLE_KEYWORD_RE` to
    begin with)."""
    target_offset = _element_start_after_keyword(text, kw.end())
    if target_offset >= len(text) or text[target_offset] == "(":
        return None
    target = _lex_target_identifier(text, target_offset)
    if target is None:
        return None
    pos = _COPY_WS_RE.match(text, target[1]).end()
    if pos < len(text) and text[pos] == "(":
        end = _skip_balanced_parens(text, pos)
        if end is None:
            return None
        pos = _COPY_WS_RE.match(text, end).end()
    direction = _COPY_DIRECTION_FROM_RE.match(text, pos)
    return None if direction is None else direction.start()


# ADR-011 D6.7.3's third and last bare-verb family
# (GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06):
# `GRANT|REVOKE <privileges> ON [TABLE] <table> [, ...] TO|FROM <role>`. As with
# `TRUNCATE` and `COPY` the target follows no table-position keyword of its own --
# `ON` is deliberately absent from `_TABLE_POSITION_KEYWORDS` because a
# `JOIN ... ON` condition is not a table position -- so the family needs its own
# context-sensitive signal source, and that context sensitivity is the whole of
# what tells the two `ON`s apart.
#
# Reproduced against this source immediately before this increment (re-executed by
# this session, not quoted from a record):
#
#   GRANT SELECT ON bil_invoices TO r      zero positions -> ERROR/2 I-1 backstop
#   REVOKE SELECT ON bil_invoices FROM r   ONE position, resolving to the *role*
#                                          `r` via the grantee `FROM` -> ERROR/2
#                                          MODULE_DEPS_TABLE_UNATTRIBUTED
#
# -- i.e. a statement handing another module's table to a role could only be called
# uninspectable, or, worse, reported the grantee as the unattributed table. Neither
# names the `CROSS_DOMAIN_SQL_IMPORT` the billing target earns, and the REVOKE row
# is a false attribution of a table nobody wrote (the shape the `ONLY` and
# `TRUNCATE`-privilege increments each removed in their own family).
#
# Scoping is `_grant_revoke_object_on_match` below, and it is deliberately NOT "any
# `ON` in SQL-ish text": only the FIRST `ON` after a `GRANT`/`REVOKE` keyword, and
# only when everything between the two is privilege-list text. An ordinary
# `JOIN ... ON` condition is therefore unreachable -- in text with no GRANT/REVOKE
# there is no candidate at all, and in text carrying both, the gap to the JOIN's
# `ON` runs through statement separators and comparison operators the gap pattern
# excludes.
#
# `TABLE`/the non-table object types are matched at the `ON`'s own target offset
# (never searched for), exactly as `_truncate_table_position_matches` matches its
# two exclusions, so the decision stays structural and local.
#
# RESIDUAL, out of this increment's scope and PRE-EXISTING -- measured on a
# throwaway copy with this increment reverted, not assumed: a privilege name that
# is itself a `_TABLE_KEYWORD_RE`/`REFERENCES` signal is still read as that
# signal, so `GRANT UPDATE ON mem_roster TO r` yields an `UPDATE` position
# resolving to the reserved word `ON` (D3.2 state 6, ERROR) and
# `GRANT REFERENCES ON mem_roster TO r` the same through `REFERENCES`. In a list
# spelling (`GRANT SELECT, INSERT, UPDATE ON a, b TO r`) that stray signal's own
# comma walk also re-counts the object list's second element, so the D8 figure
# double-counts it. `TRUNCATE` is the one privilege name already excluded, by its
# own source. This increment neither creates nor widens that defect -- those
# positions are identical with and without it -- and it does not narrow it either:
# the only change is that the statement's real target is now attributed beside the
# stray position, so the verdict stays a fail-closed ERROR at exit 2 in both
# states and no such form becomes clean. Closing it means giving
# `_table_keyword_position_matches` and the `REFERENCES` source the same
# privilege-name context sensitivity `_truncate_table_position_matches` has, which
# is a change to those two families and belongs to its own increment.
_REVOKE_KEYWORD_RE = re.compile(r"\bREVOKE\b", re.IGNORECASE)
# The grantee-list introducer of a `REVOKE`. Deliberately the same `\bFROM\b`
# boundary `_TABLE_KEYWORD_RE` itself matches on, so the exclusion offset computed
# from it is exactly a `_TABLE_KEYWORD_RE` match's own `start()`.
_GRANTEE_FROM_RE = re.compile(r"\bFROM\b", re.IGNORECASE)
# The optional `TABLE` keyword in front of a GRANT/REVOKE object list, consumed by
# the grantee walk with its required whitespace. `TABLE_x` is one identifier and
# does not match.
_GRANT_OBJECT_TABLE_KEYWORD_RE = re.compile(r"TABLE\s+", re.IGNORECASE)
# The privilege list between the verb and its object `ON`: privilege words, `,`
# separators, and an optional parenthesised column list (`GRANT SELECT (col) ON
# t`), including a double-quoted column name. Nothing else -- no `;`, no `*`, no
# comparison operator, no string literal -- which is what keeps a `JOIN ... ON`
# condition elsewhere in the same text from being read as a GRANT object clause.
_GRANT_PRIVILEGE_GAP_RE = re.compile(r"[\w\s,()\"]*")
# The object types a GRANT/REVOKE `ON` can introduce that are NOT a bare table
# target this source may claim:
#
#   * `TABLE` -- the literal keyword is already a `_TABLE_KEYWORD_RE` signal and
#     already a `_LIST_POSITION_SIGNALS` member, so its comma list is already
#     walked. Yielding here as well would emit a second stream of positions for the
#     same targets, the first of them resolving to the word `TABLE` -- the same
#     double-count `_truncate_table_position_matches` excludes for `TRUNCATE
#     TABLE x`.
#   * every other entry -- `ON SCHEMA s`, `ON SEQUENCE s`, `ON ALL TABLES IN
#     SCHEMA s`, `ON DATABASE d`, ... -- names no single table target at all, so
#     lexing one here would resolve the position to the object-type keyword itself
#     and reach D3.2 state 6: an ERROR naming a table nobody wrote, in place of the
#     I-1 refusal these forms have today.
#
# Excluding is the fail-closed direction in both cases, and unconditionally so:
# `_has_bare_table_verb_form` still fires on any GRANT/REVOKE carrying an `ON`
# (see its own docstring), so an excluded form with no other recognised position
# keeps its pre-increment ERROR/2 I-1 backstop refusal rather than becoming a clean
# PASS. The cost of an over-broad entry here is therefore a retained ERROR, never a
# silent pass -- which is why an unquoted table genuinely named after one of the
# unreserved words below (`domain`, `routine`, ...) is an acceptable loss: it stays
# refused, exactly as it is today. A *quoted* `"type"`/`"domain"` target does not
# match at all (the offset holds `"`, not the keyword) and so still yields, the same
# losslessness argument the `TRUNCATE`-privilege `ON` exclusion rests on.
_GRANT_REVOKE_NON_TABLE_TARGET_RE = re.compile(
    r"(?:TABLE|TABLESPACE|ALL|DATABASE|DOMAIN|FOREIGN|FUNCTION|LANGUAGE|LARGE"
    r"|PARAMETER|PROCEDURE|ROUTINE|SCHEMA|SEQUENCE|TYPE)\b",
    re.IGNORECASE,
)


def _grant_revoke_object_on_match(text: str,
                                  kw: re.Match[str]) -> re.Match[str] | None:
    """The object-clause `ON` belonging to the `GRANT`/`REVOKE` keyword match `kw`,
    or `None` if `kw` has none.

    Positively computed, never guessed: it is the first `_ON_KEYWORD_RE` match
    after the verb, and only if the text between the verb and it is privilege-list
    text (`_GRANT_PRIVILEGE_GAP_RE`). Because that gap can only grow, a failing
    first `ON` means no later one can qualify either, so this returns `None` rather
    than scanning on -- there is exactly one object clause per statement.

    This is the one place the family's `ON` is identified. Both consumers go
    through it -- the signal source below, and the REVOKE grantee-`FROM`
    exclusion -- so the position stream and that exclusion cannot come to
    different conclusions about which `ON` (if any) is the object clause."""
    on = _ON_KEYWORD_RE.search(text, kw.end())
    if on is None:
        return None
    if _GRANT_PRIVILEGE_GAP_RE.fullmatch(text, kw.end(), on.start()) is None:
        return None
    return on


def _grant_revoke_on_table_position_matches(text: str) -> Iterator[re.Match[str]]:
    """ADR-011 D6.7.2/D6.7.3 context-sensitive `GRANT`/`REVOKE ... ON` signal
    source -- the last of the bare-verb families, modelled on
    `_truncate_table_position_matches` and `_copy_table_position_matches` above.

    Yields the `ON` match itself (not the verb), because `ON` is what the target
    follows: the shared `_table_list_positions` walk then reads the target list
    from the keyword's own end exactly as it does for every other signal, so this
    family's comma list, its `ONLY` modifiers and its unresolvable elements all
    come from that one walk rather than from a second parser. `ON` is a
    `_LIST_POSITION_SIGNALS` member for that reason and that reason only.

    Two things are excluded, each because the position is accounted for elsewhere
    or is not a single table target at all: an `ON` whose target offset holds a
    `_GRANT_REVOKE_NON_TABLE_TARGET_RE` keyword (see that pattern's own comment),
    and an `ON` that is not a GRANT/REVOKE object clause in the first place (see
    `_grant_revoke_object_on_match`) -- which is what leaves an ordinary
    `JOIN ... ON` condition untouched.

    A dangling `ON` with no target at all (`GRANT SELECT ON`, `GRANT SELECT ON;`)
    is yielded, never excluded -- D6.7.1's safe direction: the shared walk records
    exactly one *unresolved* position for it, so the statement stays ERROR, and the
    classification moves from the statement-wide I-1 backstop to the per-position
    dangling refusal that can name the signal and its offset.

    One `ON` is yielded at most once. `REVOKE GRANT OPTION FOR SELECT ON mem_t
    FROM r` carries two verb keywords whose object clause is the *same* `ON`, and
    yielding it twice would emit two position streams for one target list -- the
    double-count the `TRUNCATE TABLE` exclusion exists to prevent, reached here by
    a different route."""
    seen: set[int] = set()
    for kw in _GRANT_REVOKE_RE.finditer(text):
        on = _grant_revoke_object_on_match(text, kw)
        if on is None or on.start() in seen:
            continue
        seen.add(on.start())
        if _GRANT_REVOKE_NON_TABLE_TARGET_RE.match(
                text, _element_start_after_keyword(text, on.end())):
            continue
        yield on


# ADR-011 D6.8.1, as above. The declared pattern is `_ON_KEYWORD_RE` and not
# `_GRANT_REVOKE_RE`: this source *iterates* the verb keywords but *yields* the
# object clause's own `ON` match, and the declaration must name the pattern whose
# matches reach the merge point, since that is the token the suppression predicate
# compares. Naming the verb pattern here would put `GRANT`/`REVOKE` into the derived
# union, and `GRANT` is a privilege-vocabulary member -- it would widen the
# suppressible set to a token no source ever yields.
_grant_revoke_on_table_position_matches.signal_keyword_pattern = (  # type: ignore[attr-defined]
    _ON_KEYWORD_RE)


def _revoke_grantee_exclusion_offset(text: str, kw: re.Match[str]) -> int | None:
    """The offset of the `FROM` that introduces the grantee list of the `REVOKE`
    keyword match `kw`, if one is *positively computed* for it -- otherwise `None`.

    The same offset-equality predicate `_copy_direction_exclusion_offset` is for
    `COPY`'s direction `FROM`, for the same reason: `REVOKE ... FROM <role>` names
    a role, never a table, so leaving that `FROM` in the stream resolves a table
    position for something nobody wrote. That is not hypothetical -- it is the
    measured pre-increment behaviour of `REVOKE SELECT ON bil_invoices FROM r`,
    whose only position was the role `r` at D3.2 state 6 while the billing table it
    revokes on went unexamined.

    Bounded the way COPY's is, by a walk and an anchored match -- not by a search
    (R1-F01/R2-N01 P0). Starting at the statement's own object-clause `ON`
    (`_grant_revoke_object_on_match`), it consumes the object list positively: an
    optional `TABLE` keyword, then one `_lex_target_identifier` target (the shared
    `ONLY`-modifier-then-identifier seam) per `,`-separated element
    (`_LIST_ITEM_CONTINUATION_RE`, the shared list walk's own continuation). Only at
    the offset where that list ends is `_GRANTEE_FROM_RE` `.match`ed -- never
    `.search`ed -- so the offset returned is a `FROM` the object list itself leads
    into, and is exactly the `start()` of the `_TABLE_KEYWORD_RE` match the wrapper
    below is filtering.

    `None` -- no exclusion, the `FROM` stays a table position, D6.7.1's safe
    direction and the one D6.7.2's accounting can then see -- whenever the walk
    cannot reach a grantee `FROM` positively: no object clause at all (`REVOKE
    admin FROM r`, a role revocation, unchanged), a dangling or truncated clause
    (`REVOKE SELECT ON`, `... ON a,`), a clause that is not a plain table list
    (`REVOKE ALL ON ALL TABLES IN SCHEMA s FROM r` stops after `ALL`), or a clause
    followed by anything other than `FROM` (`... ON a TO r`, or another statement
    written after it with no `;`). The unbounded search this replaced returned the
    next `FROM` anywhere in the subject in those cases, which deleted an unrelated
    statement's table position from the stream before the accounting could see it.

    The disclosed consequence for the `ALL TABLES IN SCHEMA` spelling: its grantee
    `FROM` is no longer excluded, so it now resolves to the role and ends at D3.2
    state 6 where it used to end at the I-1 backstop. ERROR exit 2 either way.

    This grantee-FROM exclusion and ADR-011 D6.8's privilege-list suppression are
    two different mechanisms at two different layers: this function computes an
    offset-equality filter applied inside index 0's wrapper
    (_table_keyword_position_matches), excluding a specific FROM before it becomes
    a signal; D6.8 suppresses privilege-name signals at the merge point
    (_table_position_results) after all sources have yielded. They are deliberately
    layered defences, not alternatives."""
    on = _grant_revoke_object_on_match(text, kw)
    if on is None:
        return None
    pos = _element_start_after_keyword(text, on.end())
    table_keyword = _GRANT_OBJECT_TABLE_KEYWORD_RE.match(text, pos)
    if table_keyword is not None:
        pos = table_keyword.end()
    while True:
        target = _lex_target_identifier(text, pos)
        if target is None:
            return None
        pos = target[1]
        continuation = _LIST_ITEM_CONTINUATION_RE.match(text, pos)
        if continuation is None:
            break
        pos = continuation.end()
    grantee = _GRANTEE_FROM_RE.match(text, _COPY_WS_RE.match(text, pos).end())
    return None if grantee is None else grantee.start()


def _table_keyword_position_matches(text: str) -> Iterator[re.Match[str]]:
    """Qualified COPY decision §4.1 context-sensitive wrapper around `_TABLE_KEYWORD_RE`,
    replacing the bare `_TABLE_KEYWORD_RE.finditer` entry at
    `_TABLE_POSITION_SIGNAL_SOURCES` index 0 (decision record §4.1 item 4).

    Yields every `_TABLE_KEYWORD_RE` match in `text` unchanged, in the same
    order, **except** a `FROM` match sitting exactly at a top-level
    table-target `COPY`'s own positively-computed direction offset
    (`_copy_direction_exclusion_offset` above) -- `FROM -> STDIN`/`STDOUT`/
    `PROGRAM`/a path is a direction token, never a table position (decision
    record §1.2), so leaving it in the stream would resolve to a false table
    position for a table nobody wrote.

    The exclusion set is collected once per call, from every `COPY` match in
    `text` independently of whether `_copy_table_position_matches` itself
    would yield that match -- a query-form `COPY` computes no exclusion
    offset at all (see that function's own `None` return there), so it can
    never remove an unrelated statement's ordinary `FROM`. The predicate
    below is `match.start()` set membership -- offset equality -- never a
    token-content check, per the decision record's explicit prohibition on
    pattern-matching `STDIN`/`STDOUT`/`PROGRAM`/path spellings. `JOIN`/`INTO`/
    `UPDATE`/`TABLE` matches are never candidates for exclusion at all (only
    `FROM` is checked), and every one of them is yielded unchanged.

    GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06 adds the second, structurally
    identical exclusion to the same set: a `REVOKE`'s own grantee-list `FROM`
    (`_revoke_grantee_exclusion_offset` above), which introduces a *role*, never a
    table. The same filter shape as COPY's -- an offset computed per keyword match,
    offset equality, only `FROM` ever checked -- so this stays one filter over one
    stream rather than a second wrapper. The REVOKE offset is bounded the way
    COPY's is: a positive walk of the REVOKE's own object list, then an anchored
    `.match` of `FROM` at the offset where the list ends, and `None` (the `FROM`
    retained) where that cannot be computed. It was an unbounded `.search` for the
    next `FROM` until R1-F01/R2-N01; it is not one now. The two exclusion sets are
    disjoint in practice and need not be: membership is a union, and an offset
    excluded for either reason is excluded once."""
    excluded = {
        offset for kw in _COPY_KEYWORD_RE.finditer(text)
        if (offset := _copy_direction_exclusion_offset(text, kw)) is not None
    }
    excluded |= {
        offset for kw in _REVOKE_KEYWORD_RE.finditer(text)
        if (offset := _revoke_grantee_exclusion_offset(text, kw)) is not None
    }
    for match in _TABLE_KEYWORD_RE.finditer(text):
        if match.group().upper() == "FROM" and match.start() in excluded:
            continue
        yield match


# ADR-011 D6.8.1, as above: this source's keyword pattern, declared at its own body.
_table_keyword_position_matches.signal_keyword_pattern = (  # type: ignore[attr-defined]
    _TABLE_KEYWORD_RE)


# The shared ADR-011 D6.7.2 accounting seam: every entry is an independent
# table-position signal source, and every signal any of them yields is turned
# into positions by the one `_positions_for_signal` dispatch below -- so the
# single `_table_position_results` stream that extraction, the dangling-keyword
# refusal and the live scanner all read cannot see a different signal set
# depending on which consumer is asking.
#
# `_table_keyword_position_matches` (the qualified decision's wrapper around
# `_TABLE_KEYWORD_RE`, GATE2-R2-N01-D67-COPY-DIRECTION-QUALIFIED-DECISION-2026-10-06)
# is first so position order is unchanged from the previous increment (a `FROM`
# position still precedes the `REFERENCES`/`USING` positions of the same
# statement, which several pinned assertions read directly) -- it still yields
# every non-excluded `_TABLE_KEYWORD_RE` match at that same index 0, in the same
# order. `_copy_table_position_matches` is appended LAST, per decision record
# §4.1 item 2, for the identical reason: appending rather than inserting leaves
# every existing position-order assertion unchanged.
# `_grant_revoke_on_table_position_matches` (GATE2-R2-N01-D67-GRANT-REVOKE-ON-
# 2026-10-06) is appended after it on that same rule -- every pre-existing
# position's order relative to every other is untouched, and this family's own
# positions are the last in the stream. COPY's own "is it last" pin therefore
# becomes "is it second-to-last", which is still an exact index; the property that
# control protects is that no new source is inserted *before*
# `_table_keyword_position_matches` at index 0.
_TABLE_POSITION_SIGNAL_SOURCES: tuple[Callable[[str], Iterator[re.Match[str]]], ...] = (
    _table_keyword_position_matches,
    _REFERENCES_KEYWORD_RE.finditer,
    _using_table_position_matches,
    _truncate_table_position_matches,
    _copy_table_position_matches,
    _grant_revoke_on_table_position_matches,
)

# ADR-011 D6.7.3: the signals whose table position is a *list* -- one signal
# introduces one position per same-depth comma element, all walked by the single
# shared `_table_list_positions`. Every other recognised signal carries one
# target and goes through `_single_identifier_position`. Membership here is the
# only thing that distinguishes the two, and it is checked in one place
# (`_positions_for_signal`), so no signal can be a list for extraction and a
# single target for the refusal.
#
# GATE2-R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-FOUR-SIGNALS (this increment) adds
# the four remaining comma-list signals -- `INTO`, `TABLE`, `UPDATE` and
# `REFERENCES` -- as membership changes to this one frozenset and nothing else.
# Each was a recognised signal already, so the *first* element of its list was
# always a position; only the continuation was out of reach, which is why
# `INSERT INTO mem_t, bil_invoices SELECT 1`, `DROP TABLE mem_t, bil_invoices`,
# `UPDATE mem_t, bil_invoices SET x = 1` and `CREATE TABLE mem_t (c int
# REFERENCES mem_a, bil_invoices)` each reached PASS exit 0 with the billing
# target absent from the stream entirely -- reproduced on both the `.py`
# string-literal and `.sql` file surfaces immediately before this increment
# (`GATE2-R2-N01-D67-REMAINING-FAMILIES-D8-RECONCILIATION-2026-10-06.md`, and
# re-run directly by this session). That is D6.7's partial-extraction asymmetry
# again, in four more families: `TABLE mem_t`/`INTO mem_t`/`UPDATE mem_t`
# extracting cleanly disarmed the accounting for the element beside it.
#
# The point of the shared walk is that this is all the change needs to be: no
# per-keyword continuation copy is added here, and none can be, because
# `_positions_for_signal` consults this set in exactly one place. `ONLY` is
# deliberately still absent and always will be: it is a modifier consumed inside
# the shared walk's own target lexing, never a signal introducing a position of
# its own, so adding it here would double-count the target it modifies
# (GATE2-R2-N01-D67-ONLY-MODIFIER-SHARED-TARGET-WALK-2026-10-06).
#
# GATE2-R2-N01-D67-TRUNCATE-BARE-VERB-SIGNAL-2026-10-06 adds `TRUNCATE`, the first
# of D6.7.3's bare-verb families. It needed two changes and no third: its own
# context-sensitive signal source (`_truncate_table_position_matches` above, since
# it has no table-position keyword of its own to be found by) and membership here,
# so its comma list, its `ONLY` modifiers and its unresolvable elements all go
# through the same `_table_list_positions` every other list signal uses.
#
# GATE2-R2-N01-D67-COPY-DIRECTION-QUALIFIED-DECISION-2026-10-06 adds `COPY`, the
# second of D6.7.3's bare-verb families, the identical way: its own
# context-sensitive signal source (`_copy_table_position_matches` above) and
# membership here, nothing else.
#
# GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06 adds `ON`, the last of them, the
# same two ways and no third: its own context-sensitive signal source
# (`_grant_revoke_on_table_position_matches` above, which is also what keeps a
# `JOIN ... ON` condition out of the stream entirely) and membership here, so
# `GRANT SELECT ON mem_roster, ONLY bil_invoices TO r` gets the comma
# continuation, the modifier consumption and the unresolved-element rule from the
# one shared walk. The member is the `ON` keyword rather than `GRANT`/`REVOKE`
# because `ON` is what the target list follows -- the walk reads from the yielded
# keyword's own end, so yielding the verb would read the privilege list as a table
# list. Every signal in `_TABLE_POSITION_SIGNAL_SOURCES` is now a member here.
_LIST_POSITION_SIGNALS = frozenset({
    "FROM", "JOIN", "USING", "INTO", "TABLE", "UPDATE", "REFERENCES", "TRUNCATE",
    "COPY", "ON",
})


def _single_identifier_position(text: str, keyword: re.Match[str]) -> _TablePositionResult:
    """One recognised table position for a signal carrying a single target --
    i.e. any recognised signal that is not a `_LIST_POSITION_SIGNALS` member.
    Resolved or not, it is always a record: a signal with no well-formed
    identifier after it yields an unresolved position rather than disappearing
    from the stream.

    No currently-recognised signal reaches here -- every member of every
    `_TABLE_POSITION_SIGNAL_SOURCES` entry is a `_LIST_POSITION_SIGNALS` member
    as of GATE2-R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-FOUR-SIGNALS -- so this
    deliberately reads a bare identifier and not a target: the `ONLY` modifier
    cannot appear after a signal that does not exist yet. A future single-target
    signal that *can* carry `ONLY` must switch this to
    `_target_identifier_after_keyword`/`_unresolved_target_reason`, the same seam
    the list walk uses, rather than consuming the modifier a second way."""
    found = _identifier_after_keyword(text, keyword.end())
    element_start = _element_start_after_keyword(text, keyword.end())
    if found is None:
        return _TablePositionResult(
            keyword.group(), keyword.start(), element_start,
            None, _NO_IDENTIFIER_AFTER_KEYWORD,
        )
    return _TablePositionResult(
        keyword.group(), keyword.start(), element_start, found[0], None,
    )


def _positions_for_signal(text: str, keyword: re.Match[str]) -> list[_TablePositionResult]:
    """Every table position introduced by one recognised signal match -- the
    single dispatch every signal from every `_TABLE_POSITION_SIGNAL_SOURCES`
    entry goes through (GATE2-R04-GATE2-R2-N01-D67-SHARED-LIST-WALK-JOIN-USING).

    A `_LIST_POSITION_SIGNALS` member contributes every element of its
    same-depth comma list via the shared `_table_list_positions` walk; any other
    signal contributes exactly one single-identifier position. Keeping this
    decision in one function is what makes the list mechanism shared rather than
    reimplemented per keyword: `_table_position_results` below has no per-keyword
    branch at all, so a new list signal cannot be wired into extraction while
    the dangling-keyword refusal keeps treating it as a single target."""
    if keyword.group().upper() in _LIST_POSITION_SIGNALS:
        return _table_list_positions(text, keyword)
    return [_single_identifier_position(text, keyword)]


# ADR-011 D6.8: privilege-list signal suppression (bounded, lossless, fail-closed)
#
# D6.8.2 check 3: the closed PostgreSQL privilege vocabulary. This is the complete
# set of privilege names plus GRANT OPTION FOR modifier words; no other identifier
# is accepted at depth 0 in a privilege-list region.
_PG_PRIVILEGE_VOCABULARY = frozenset({
    "ALL", "ALTER", "CONNECT", "CREATE", "DELETE", "EXECUTE", "FOR", "GRANT",
    "INSERT", "MAINTAIN", "OPTION", "PRIVILEGES", "REFERENCES", "SELECT", "SET",
    "SYSTEM", "TEMP", "TEMPORARY", "TRIGGER", "TRUNCATE", "UPDATE", "USAGE",
})

# D6.8.1: the suppressible set is the derived intersection of PostgreSQL privilege
# names and the union of `_TABLE_POSITION_SIGNAL_SOURCES`' keyword tokens -- derived
# from the sources themselves, never hand-listed beside them. A hand-list is what
# D6.8.1's own Alternatives row rejects, and for the stated reason: it "cannot notice
# a future signal keyword that is also a privilege name".
#
# The derivation reads each source's *declared* keyword pattern -- the
# `signal_keyword_pattern` attribute assigned at each wrapper's own `def` above, or
# `__self__` for a bare `re.Pattern` method entry such as index 1's
# `_REFERENCES_KEYWORD_RE.finditer` -- and parses the tokens out of that pattern. So a
# keyword added to any backing alternation (`_TABLE_KEYWORD_RE`'s, say) enters the
# union with no edit here at all, which is the property the hand-list lacked.
#
# Today the intersection is exactly {UPDATE, REFERENCES, TRUNCATE}.
_SIGNAL_KEYWORD_PATTERN_ATTR = "signal_keyword_pattern"

# The one shape every signal keyword pattern in this file is written in:
# `\bTOK\b` or `\b(?:TOK|TOK|...)\b`. Parsed strictly and anchored, so a future
# keyword pattern written in some other shape raises below rather than silently
# yielding a wrong token set -- D6.8.4's fail-closed form applied to the derivation
# itself.
_SIGNAL_KEYWORD_PATTERN_SHAPE_RE = re.compile(
    r"\\b(?:\(\?:(?P<alternation>[A-Za-z]+(?:\|[A-Za-z]+)*)\)"
    r"|(?P<single>[A-Za-z]+))\\b")


def _signal_source_keyword_pattern(
    source: Callable[[str], Iterator[re.Match[str]]],
) -> re.Pattern[str]:
    """The compiled keyword pattern whose matches `source` yields.

    Two shapes, both mechanical -- nothing here is keyed on a source's name:

      * a bare `re.Pattern` method entry carries its own pattern on `__self__`
        (`_REFERENCES_KEYWORD_RE.finditer`, index 1);
      * a wrapper function declares its pattern on itself, beside the body that
        drives it (`<wrapper>.signal_keyword_pattern`).

    A source that offers neither raises `ValueError` at import time, by way of
    `_SUPPRESSIBLE_PRIVILEGE_SIGNALS`' module-level evaluation. That is deliberate and
    is the point of deriving rather than hand-listing: a future signal family added
    without declaring its keywords cannot be quietly left out of D6.8.1's suppressible
    set, because the gate refuses to load at all."""
    declared = getattr(source, _SIGNAL_KEYWORD_PATTERN_ATTR, None)
    if isinstance(declared, re.Pattern):
        return declared
    bound = getattr(source, "__self__", None)
    if isinstance(bound, re.Pattern):
        return bound
    raise ValueError(
        f"ADR-011 D6.8.1: table-position signal source "
        f"{getattr(source, '__name__', source)!r} declares no keyword pattern, so its "
        f"keyword tokens cannot be derived. Assign {_SIGNAL_KEYWORD_PATTERN_ATTR!r} on "
        f"it, beside its own body as the existing sources do; the suppressible set must "
        f"never be hand-listed."
    )


def _signal_source_keyword_tokens(
    sources: Sequence[Callable[[str], Iterator[re.Match[str]]]],
) -> frozenset[str]:
    """ADR-011 D6.8.1 half (b): the union of the keyword tokens of every signal source
    in `sources`, upper-cased, read off each source's declared pattern.

    Every such pattern is matched case-insensitively, so the tokens are compared
    upper-cased throughout (`_is_privilege_signal_suppressed` upper-cases
    `kw.group()` for the same reason). A pattern compiled *without* `re.IGNORECASE`
    would make that mapping unsound, so it raises rather than being normalised away."""
    tokens: set[str] = set()
    for source in sources:
        pattern = _signal_source_keyword_pattern(source)
        if not pattern.flags & re.IGNORECASE:
            raise ValueError(
                f"ADR-011 D6.8.1: signal keyword pattern {pattern.pattern!r} is "
                f"case-sensitive, so its tokens cannot be compared upper-cased against "
                f"the privilege vocabulary"
            )
        shape = _SIGNAL_KEYWORD_PATTERN_SHAPE_RE.fullmatch(pattern.pattern)
        if shape is None:
            raise ValueError(
                f"ADR-011 D6.8.1: signal keyword pattern {pattern.pattern!r} is not in "
                f"the \\bTOK\\b / \\b(?:TOK|...)\\b shape this derivation parses, so "
                f"its keyword tokens cannot be derived"
            )
        alternation = shape.group("alternation")
        raw = (alternation.split("|") if alternation is not None
               else [shape.group("single")])
        tokens.update(token.upper() for token in raw)
    return frozenset(tokens)


def _compute_suppressible_privilege_signals(
    sources: Sequence[Callable[[str], Iterator[re.Match[str]]]] | None = None,
    vocabulary: frozenset[str] = _PG_PRIVILEGE_VOCABULARY,
) -> frozenset[str]:
    """ADR-011 D6.8.1: the suppressible set -- the intersection of the closed
    PostgreSQL privilege-name vocabulary (half (a)) and the union of every signal
    source's keyword tokens (half (b)).

    `sources` defaults to the live `_TABLE_POSITION_SIGNAL_SOURCES`. It is a parameter
    so the derivation can be exercised over a *hypothetical* source set, which is the
    only way to establish by a non-tautological test that a future signal keyword which
    is also a privilege name really would enter this set rather than be silently
    omitted. Nothing in the live path passes it."""
    if sources is None:
        sources = _TABLE_POSITION_SIGNAL_SOURCES
    return frozenset(_signal_source_keyword_tokens(sources) & vocabulary)


_SUPPRESSIBLE_PRIVILEGE_SIGNALS = _compute_suppressible_privilege_signals()


def _privilege_list_region(text: str, verb: re.Match[str]) -> tuple[int, int] | None:
    """ADR-011 D6.8.2: compute the privilege-list region R = [verb.end(), on.start())
    for the given GRANT/REVOKE verb match, if one is positively computed —
    otherwise None.

    The region is the interval between the verb and its object-clause ON, and
    it is positively computed if and only if ALL of the following hold:

    1. _GRANT_PRIVILEGE_GAP_RE.fullmatch succeeds (character-class precondition)
    2. Parentheses are balanced within R and depth is 0 at on.start()
    3. Every depth-0 identifier-shaped token casefolds into _PG_PRIVILEGE_VOCABULARY
    4. No " or non-identifier/non-separator appears at depth 0

    If any check fails, returns None (D6.8.4: uncertainty fails closed, signals
    retained). The open upper end (on.start() is NOT in the region) is normative
    and places the object ON strictly outside, so it can never be suppressed.

    This vocabulary check is the load-bearing defence, not the interval
    arithmetic: _grant_revoke_object_on_match can span an entire unrelated
    statement when no depth-0 semicolon appears, and an interval-only rule
    would suppress that statement's real table positions."""
    on = _grant_revoke_object_on_match(text, verb)
    if on is None:
        return None

    a, b = verb.end(), on.start()

    # Check 1: character-class precondition (the existing gap regex)
    if _GRANT_PRIVILEGE_GAP_RE.fullmatch(text, a, b) is None:
        return None

    # Checks 2, 3, 4: single left-to-right scan maintaining parenthesis depth
    depth = 0
    pos = a

    while pos < b:
        ch = text[pos]

        if ch == '(':
            depth += 1
            pos += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:  # Check 2: unbalanced parens
                return None
            pos += 1
        elif ch == '"':  # Check 4: no " at depth 0
            if depth == 0:
                return None
            pos += 1
        elif ch.isspace() or ch == ',':  # separators
            pos += 1
        elif ch.isalpha() or ch == '_':  # identifier start at depth 0
            if depth == 0:
                # Collect the full identifier token
                ident_start = pos
                while pos < b and (text[pos].isalnum() or text[pos] == '_'):
                    pos += 1
                token = text[ident_start:pos].upper()
                # Check 3: must be in the closed privilege vocabulary
                if token not in _PG_PRIVILEGE_VOCABULARY:
                    return None
            else:
                # At depth >= 1 (column list), skip identifier without checking
                while pos < b and (text[pos].isalnum() or text[pos] == '_'):
                    pos += 1
        elif ch.isdigit():  # Check 4: no numeric literal at depth 0
            if depth == 0:
                return None
            # At depth >= 1, skip number
            while pos < b and text[pos].isdigit():
                pos += 1
        else:  # Check 4: any other non-separator at depth 0
            if depth == 0:
                return None
            pos += 1

    # Check 2: depth must be 0 at the region's upper end (on.start())
    if depth != 0:
        return None

    # All checks passed — return the region with open upper end
    return (a, b)


def _is_privilege_signal_suppressed(text: str, kw: re.Match[str],
                                    regions: list[tuple[int, int]]) -> bool:
    """ADR-011 D6.8.3: the suppression predicate. Returns True if and only if
    signal match `kw` should be suppressed (not contributed to the position
    stream), which requires ALL FOUR of:

    1. kw.group().upper() is in the derived suppressible set (D6.8.1)
    2. There exists a positively-computed region R = [a, b) with
       a <= kw.start() and kw.end() <= b
    3. kw.start() sits at parenthesis depth 0 relative to the region's lower end
    4. Nothing else — no token-content check on what follows kw, no spelling
       test, no fallback

    D6.8.4: uncertainty fails closed. If any condition is uncertain or fails,
    returns False (signal is retained)."""
    # Condition 1: keyword must be in the suppressible set
    if kw.group().upper() not in _SUPPRESSIBLE_PRIVILEGE_SIGNALS:
        return False

    # Condition 2: keyword must lie wholly within a positively-computed region
    kw_start, kw_end = kw.start(), kw.end()
    region_match = None
    for a, b in regions:
        if a <= kw_start and kw_end <= b:
            region_match = (a, b)
            break

    if region_match is None:
        return False

    # Condition 3: kw.start() must be at parenthesis depth 0 relative to the
    # region's lower end. Scan from region start to kw.start() tracking depth.
    a, b = region_match
    depth = 0
    for pos in range(a, kw_start):
        if text[pos] == '(':
            depth += 1
        elif text[pos] == ')':
            depth -= 1
            # Negative depth at this point means the region itself was malformed,
            # but we already accepted it above — this is defensive depth tracking,
            # not region validation. If depth goes negative, fail closed.
            if depth < 0:
                return False

    # All four conditions are satisfied only at depth zero.
    return depth == 0


@dataclass
class _SuppressionCounts:
    """ADR-011 D6.8.6's suppression accounting sink, mutated in place by
    `_table_position_results` for the same reason `_TableRefCounts` and
    `_ZeroTableCounts` are: the figure must **aggregate across every subject this run
    handed the scanner** and must survive into the ERROR report built by
    `run_module_deps_gate`'s `except GateInputError` handler, rather than being a
    per-call value the next call overwrites.

    That aggregation is the whole obligation. D6.8.6 requires the count to be
    "disclosed under D8 on every run including PASS", and a run scans many subjects --
    `.sql` files, `str` literals, decoded `bytes` literals -- so a per-subject figure
    discloses the last subject's suppression and silently drops every earlier one. A
    narrowing that leaves no trace in the report is, in D6.8.6's own words,
    "indistinguishable, to a reader, from the silent under-extraction D6.7 exists to
    forbid"; a figure that traces only the final subject is the same defect wearing a
    number.

    `signals` counts *suppressed signals*, not statements and not distinct keywords:
    one statement suppressing both a `TRUNCATE` and an `UPDATE` contributes 2, and the
    same statement appearing in two files contributes 2. `subjects` counts the scanner
    subjects in which at least one suppression occurred, so a reader can tell one
    heavily-suppressing subject from many lightly-suppressing ones without either
    figure being a view of the other."""
    signals: int = 0
    subjects: int = 0


def _table_position_results(
    text: str, suppression: _SuppressionCounts | None = None,
) -> list[_TablePositionResult]:
    """ADR-011 D6.7.2's per-position accounting stream: one
    `_TablePositionResult` for every recognised table position in `text`, in
    order, each carrying either an identifier for D3.2 attribution or the
    reason it could not be resolved.

    This is the single seam both consumers below and the live scanner read, so
    extraction and refusal are structurally unable to see different positions
    for the same text -- the drift that let a cleanly-extracted identifier
    disarm a refusal elsewhere in the same statement. Identifiers come from
    the explicit lexer above rather than a regex, so a double-quoted segment
    (including one with an escaped embedded quote) and a 2-part or 3+-part
    name mixing quoted and unquoted segments are each captured in full, with
    quotes preserved exactly as written, or not captured at all.

    Every `_TABLE_POSITION_SIGNAL_SOURCES` entry feeds the stream, and a
    position from any of them can never be hidden by another resolving cleanly:

      * `_TABLE_KEYWORD_RE` keywords -- `FROM`/`JOIN`/`INTO`/`UPDATE`/`TABLE` --
        via the context-sensitive `_table_keyword_position_matches` wrapper,
        which excludes exactly a table-target `COPY`'s own top-level direction
        `FROM` (qualified COPY decision §4.1) and yields every other match unchanged.
      * the `REFERENCES` target.
      * the context-sensitive `DELETE ... USING` target. A `USING` opening a
        JOIN column list is excluded by that signal source itself, so it never
        becomes a position at all.
      * the context-sensitive bare-verb `TRUNCATE` target list. A `TRUNCATE`
        whose own list is already walked through the literal `TABLE` keyword, and
        a `TRUNCATE` used as a GRANT/REVOKE privilege name, are both excluded by
        that signal source itself.
      * the context-sensitive bare-verb `COPY` target list (qualified decision §4.1). A
        table-target `COPY`'s target is yielded; a query-form `COPY`
        (`COPY (SELECT ...) TO STDOUT`) is excluded by that signal source
        itself, since its target carries no table position at all.
      * the context-sensitive `GRANT`/`REVOKE ... ON` object list
        (GATE2-R2-N01-D67-GRANT-REVOKE-ON-2026-10-06). Only a GRANT/REVOKE object
        clause's own `ON` is a signal; an `ON` opening a `JOIN` condition, one
        introducing a non-table object type (`ON SCHEMA`, `ON ALL TABLES IN
        SCHEMA`), and one whose list the literal `TABLE` keyword already walks are
        all excluded by that signal source itself. A `REVOKE`'s grantee `FROM`
        names a role rather than a table and is excluded at index 0's wrapper, the
        same way a table-target `COPY`'s direction `FROM` is.

    How many positions each signal contributes is `_positions_for_signal`'s one
    decision, not this function's: a `_LIST_POSITION_SIGNALS` signal
    (`FROM`/`JOIN`/`USING`/`INTO`/`TABLE`/`UPDATE`/`REFERENCES`/`TRUNCATE`/`COPY`)
    contributes every element of its comma list through the shared
    `_table_list_positions` walk, and every other signal contributes one. An `ONLY`
    modifier in front of any of those elements is consumed by that same walk's
    target lexing and contributes no position of its own. Every
    `_LIST_POSITION_SIGNALS` member now has a source here, so no D6.7.3 list
    subcase is waiting on one.

    No signal is counted twice: the six sources match disjoint keywords, and the
    two keywords two sources could each have claimed are both resolved by
    exclusion rather than by de-duplication after the fact -- the `TABLE` of
    `TRUNCATE TABLE x` and of `GRANT SELECT ON TABLE x` is left to
    `_TABLE_KEYWORD_RE` alone by those two sources' own exclusions. The one
    keyword a single source could have yielded twice -- the shared object `ON` of
    `REVOKE GRANT OPTION FOR SELECT ON x FROM r`, which sits after both of that
    statement's verb keywords -- is de-duplicated inside that source.

    ADR-011 D6.8.6: privilege-list signal suppression happens at exactly this
    merge point, between obtaining each kw and calling `_positions_for_signal`. A
    signal that is suppressed contributes no position to the stream, and each
    suppression increments `suppression` -- the run-wide `_SuppressionCounts` sink
    `run_module_deps_gate` constructs once and threads through every subject, so the
    D8 disclosure is an aggregate over the whole run and not the last subject's
    figure. `suppression` is `None` only for the two derived views below and for
    direct unit callers, which read positions and make no disclosure; the live
    scanning path always passes the sink."""
    positions: list[_TablePositionResult] = []

    # D6.8.6: Compute all GRANT/REVOKE privilege-list regions once before the
    # loop (regions are positively computed per D6.8.2, or None on uncertainty).
    privilege_regions: list[tuple[int, int]] = []
    for verb in _GRANT_REVOKE_RE.finditer(text):
        region = _privilege_list_region(text, verb)
        if region is not None:
            privilege_regions.append(region)

    # D6.8.6: Track suppressed signals for accounting disclosure
    suppressed_privilege_signals = 0

    for source in _TABLE_POSITION_SIGNAL_SOURCES:
        for kw in source(text):
            # D6.8.6: The single suppression site. Check if this signal should
            # be suppressed as a privilege-list token before contributing it to
            # the position stream.
            if _is_privilege_signal_suppressed(text, kw, privilege_regions):
                suppressed_privilege_signals += 1
                # D6.8.4: Suppressed signals contribute nothing to the stream.
                # The accounting sees the suppression through the counter above,
                # not through an absent position (which would be silent).
                continue

            positions.extend(_positions_for_signal(text, kw))

    # D6.8.6: fold this subject's suppressions into the run-wide sink, so the D8
    # disclosure aggregates across subjects rather than reporting the last one. The
    # increment is conditional on the sink existing, never on the count: a subject
    # that suppressed nothing must leave both figures alone, while `signals == 0`
    # over a whole run is itself a disclosed claim the note makes explicitly.
    if suppression is not None and suppressed_privilege_signals:
        suppression.signals += suppressed_privilege_signals
        suppression.subjects += 1

    return positions


def _extract_table_identifiers(text: str) -> list[str]:
    """Every resolved table-position identifier in `text`, in order -- a
    derived view over `_table_position_results` above, which is where the
    actual walking happens.

    Kept as a named function because it is the layer at which the
    extraction-accounting mutation controls are pinned (a mutant that drops a
    signal source is caught here, at the layer it was introduced in, rather
    than only through the gate's verdict plumbing). It is deliberately *only*
    a projection now: an unresolved position contributes nothing here, so this
    function on its own can never be the accounting proof -- the live scanner
    reads the stream itself and compares positions to attributed identifiers
    position by position."""
    return [p.identifier for p in _table_position_results(text)
            if p.identifier is not None]


def _dangling_keywords(text: str) -> bool:
    """Whether any recognised table position in `text` went unresolved -- the
    other derived view over `_table_position_results`, and the exact
    complement of `_extract_table_identifiers` above over the same stream.

    Because both views project the same records, they cannot disagree about
    which positions exist: a signal is either resolved (its identifier is in
    the extraction view) or unresolved (it makes this view `True`), never
    neither. That equivalence is what `_TablePositionResult.__post_init__`
    enforces per record."""
    return any(p.identifier is None for p in _table_position_results(text))


# --- ADR-011 D3: pure table-identifier attribution helper (increment D1a) --------
#
# GATE2-R1-D1A-ATTRIBUTION-HELPER-2026-10-05: a standalone, pure function
# implementing ADR-011 D3's six-state identifier-attribution table.
# GATE2-R1-D1A-SCANNER-WIRING-2026-10-05 wired this function into the live
# `_scan_sql_text` path below, replacing the pre-ADR-011 `_resolve_owner` helper
# (one-dimensional, "unowned ⇒ None/benign note" -- removed, since nothing calls
# it anymore). No I/O, no global mutation, no `modules`/`cte_names` mutation; the
# same five arguments to `attribute_table_identifier` always yield the same
# `AttributionOutcome`.

# ADR-011 D3.1: a double-quoted segment preserves case exactly (quotes stripped);
# an unquoted segment is casefolded to lower case. Split first, respecting quoted
# segments, so a dot *inside* an unquoted run is still a separator while a dot
# inside a quoted segment's content is not.
#
# GATE2-R1-D1A-QUOTED-LEXER-2026-10-05: `_split_identifier_segments` previously
# used a `'"[^"]*"|[^.]+'` regex alternation. That shape mishandles an escaped
# embedded quote (SQL's `""`, one literal `"` character inside a quoted
# segment) -- confirmed by direct execution, `'"ab""cd"'` (one segment, the
# table name `ab"cd`) wrongly splits into two adjacent segments, `'"ab"'` and
# `'"cd"'`, because the regex's own closing `"` matches the first half of the
# escape pair. Rewritten below to reuse the same explicit `_lex_quoted_segment`
# scan the live extraction lexer uses, so both paths treat `""` identically --
# this is the "direct dependent helper correction" the quoted-identifier fix
# makes necessary, not a second, independent lexer.


def _split_identifier_segments(raw_identifier: str) -> list[str]:
    """Splits a possibly-quoted, dot-qualified identifier into its raw
    (not-yet-normalised) parts. A `.` is a separator only when it is not
    inside an open quote; an escaped embedded quote (`""`) inside a quoted
    segment keeps that segment open, exactly as `_lex_quoted_segment` treats
    it during live extraction. An unterminated quote is not silently dropped
    or mis-split -- the remainder of the string becomes one segment, which
    `_normalize_identifier_segment` then leaves unmatched by either the
    "fully quoted" or ordinary-bare shape, so it fails closed to
    `ATTR_UNATTRIBUTED` rather than a false clean match."""
    segments: list[str] = []
    i = 0
    n = len(raw_identifier)
    while i < n:
        if raw_identifier[i] == '"':
            lexed = _lex_quoted_segment(raw_identifier, i)
            if lexed is None:
                segments.append(raw_identifier[i:])
                break
            seg, i = lexed
            segments.append(seg)
        else:
            j = i
            while j < n and raw_identifier[j] not in (".", '"'):
                j += 1
            segments.append(raw_identifier[i:j])
            i = j
        if i < n and raw_identifier[i] == ".":
            i += 1
    return segments


def _normalize_identifier_segment(segment: str) -> str:
    """ADR-011 D3.1 (PostgreSQL semantics): a double-quoted segment preserves
    case exactly, with its quotes stripped and any escaped embedded quote
    (`""`) collapsed to the single literal `"` character it represents; an
    unquoted segment is casefolded to lower case."""
    if len(segment) >= 2 and segment[0] == '"' and segment[-1] == '"':
        return segment[1:-1].replace('""', '"')
    return segment.lower()


def _owner_by_prefix(table_part: str, modules: Mapping[str, ModuleEntry]) -> str | None:
    """Longest-matching `owned_table_prefixes` entry across every module. Kept
    separate from `_owner_by_schema` (rather than reusing `_resolve_owner`,
    which never checks both for one identifier) so a conflict between the two
    dimensions (ADR-011 D3.3 rule 4) can be detected instead of silently
    resolved by whichever check runs first."""
    best: tuple[int, str] | None = None
    for mod in modules.values():
        for prefix in mod.owned_table_prefixes:
            if table_part.startswith(prefix) and (best is None or len(prefix) > best[0]):
                best = (len(prefix), mod.name)
    return best[1] if best else None


def _owner_by_schema(schema_part: str, modules: Mapping[str, ModuleEntry]) -> str | None:
    """Exact-match owner of `schema_part` via `owned_schemas`, or `None` if no
    module declares it."""
    for mod in modules.values():
        if schema_part in mod.owned_schemas:
            return mod.name
    return None


def _is_declared_external(importer: str, modules: Mapping[str, ModuleEntry],
                          canonical: str) -> bool:
    """ADR-011 D3.5/state 5: `canonical` (already normalised, dotted form) is
    exactly one of the *importing* module's own declared
    `external_table_references` entries. `_root` and `_shared` are domain-free
    reserved importers that are never manifest-declarable (ADR-011 D4), so
    `modules.get(importer)` is always `None` for either and this is always
    `False` for them by construction, not by a special case here."""
    entry = modules.get(importer)
    if entry is None:
        return False
    return canonical in entry.external_table_references


@dataclass(frozen=True)
class AttributionOutcome:
    """ADR-011 D3.2's six terminal states, collapsed to the five ATTR_*
    constants already declared above (states 1 and 2 share `ATTR_OWNED`; the
    caller -- not this function -- decides own-vs-other by comparing `owner`
    to the scanning module's own name, exactly as `_scan_sql_text` does with
    this outcome's `owner` field). `reason` is a short, human-readable
    disclosure string for a report/test failure message; it is never used for
    control flow and its exact wording is not part of this helper's
    contract."""
    state: str
    owner: str | None = None
    reason: str = ""


def _attribute_bare_identifier(name: str, modules: Mapping[str, ModuleEntry], importer: str,
                               cte_names: frozenset[str]) -> AttributionOutcome:
    """Resolution for a single, already-normalised, unqualified name -- used
    both for a genuinely bare identifier and for a 2-part identifier whose
    schema was stripped under ADR-011 D3.3 rule 2 (default-schema stripping),
    so a bare table name and an explicitly `default_schema`-qualified name
    resolve identically. Order: CTE-local (most locally bound) -> reserved
    system prefix -> owned prefix -> declared external -> unattributed."""
    if name in cte_names:
        return AttributionOutcome(ATTR_CTE, None,
                                  f"local CTE name {name!r} (ADR-011 D3.2 state 3)")
    if name.startswith("pg_"):
        return AttributionOutcome(ATTR_SYSTEM, None,
                                  f"reserved system identifier {name!r} (ADR-011 D3.4)")
    owner = _owner_by_prefix(name, modules)
    if owner is not None:
        return AttributionOutcome(ATTR_OWNED, owner, f"owned_table_prefixes match for {name!r}")
    if _is_declared_external(importer, modules, name):
        return AttributionOutcome(
            ATTR_EXTERNAL, None,
            f"declared external_table_references entry {name!r} (module {importer!r})",
        )
    return AttributionOutcome(ATTR_UNATTRIBUTED, None, f"no module owns {name!r}")


def attribute_table_identifier(
    raw_identifier: str,
    modules: Mapping[str, ModuleEntry],
    importer: str,
    default_schema: str,
    cte_names: frozenset[str] = frozenset(),
) -> AttributionOutcome:
    """ADR-011 D3: pure identifier-to-owner attribution for one table-position
    identifier. No I/O, no SQL scanning, and no mutation of any argument -- a
    single lexical decision over its five inputs. Wired into the live
    `_scan_sql_text` path by GATE2-R1-D1A-SCANNER-WIRING-2026-10-05 (the prior
    increment, GATE2-R1-D1A-ATTRIBUTION-HELPER-2026-10-05.md, built this
    function standalone and un-wired; that is no longer the case).

    D3.1 normalisation and D3.3's resolution precedence/conflict rule are
    applied here. D3.3 rule 1 (an identifier of 3+ dotted parts) and rule 4 (a
    schema-owner/prefix-owner conflict) both resolve to `ATTR_UNATTRIBUTED` --
    the single catch-all ERROR terminal state D3.2 itself names ("state 6:
    anything else"). ADR-011's own D7 error taxonomy gives neither of those two
    conditions a distinct outcome code of its own, so both are represented
    here as `ATTR_UNATTRIBUTED` with a `reason` string naming which rule
    fired, rather than this helper inventing an undocumented seventh state."""
    segments = _split_identifier_segments(raw_identifier)
    if len(segments) >= 3:
        return AttributionOutcome(
            ATTR_UNATTRIBUTED, None,
            f"identifier {raw_identifier!r} has {len(segments)} dotted parts (ADR-011 "
            "D3.3 rule 1: 3+ parts is unattributed -- outside the ownership model "
            "entirely)",
        )
    parts = [_normalize_identifier_segment(segment) for segment in segments]
    if len(parts) == 1:
        return _attribute_bare_identifier(parts[0], modules, importer, cte_names)
    schema_part, table_part = parts
    if schema_part == default_schema:
        # ADR-011 D3.3 rule 2: default-schema stripping.
        return _attribute_bare_identifier(table_part, modules, importer, cte_names)
    if schema_part in _RESERVED_SCHEMA_NAMES or table_part.startswith("pg_"):
        return AttributionOutcome(
            ATTR_SYSTEM, None,
            f"reserved system identifier {raw_identifier!r} (ADR-011 D3.4)",
        )
    schema_owner = _owner_by_schema(schema_part, modules)
    prefix_owner = _owner_by_prefix(table_part, modules)
    if schema_owner is not None and prefix_owner is not None and schema_owner != prefix_owner:
        return AttributionOutcome(
            ATTR_UNATTRIBUTED, None,
            f"identifier {raw_identifier!r}: schema {schema_part!r} is owned by "
            f"{schema_owner!r} but table prefix resolves to {prefix_owner!r} (ADR-011 "
            "D3.3 rule 4 -- a conflict is never resolved by iteration order)",
        )
    if schema_owner is not None:
        return AttributionOutcome(ATTR_OWNED, schema_owner,
                                  f"owned_schemas entry {schema_part!r}")
    if _is_declared_external(importer, modules, f"{schema_part}.{table_part}"):
        return AttributionOutcome(
            ATTR_EXTERNAL, None,
            f"declared external_table_references entry {raw_identifier!r} "
            f"(module {importer!r})",
        )
    return AttributionOutcome(
        ATTR_UNATTRIBUTED, None,
        f"no module owns schema {schema_part!r} or a matching table prefix for "
        f"{raw_identifier!r}",
    )


@dataclass
class _TableRefCounts:
    """ADR-011 D8's "table references by D3.2 state" counters
    (GATE2-R1-F12-D8-TABLE-STATE-COUNTERS-2026-10-05), mutated in place by
    `_scan_sql_text` for the same reason `_CoverageCounts` is: whatever the run
    had actually established must survive into the ERROR report built by
    `run_module_deps_gate`'s `except GateInputError` handler, labelled as a
    minimum rather than discarded or read as a total.

    One field per D3.2 terminal state, with states 1 and 2 kept **separate** --
    they share the single `ATTR_OWNED` constant internally and are told apart
    only by comparing the resolved owner to the scanning module, which is a
    distinction a reader of the report must be able to make (state 1 is clean,
    state 2 is a FAIL `CROSS_DOMAIN_SQL_IMPORT`). Collapsing them would make the
    disclosure useless on exactly the dimension the gate exists for.

    Every field counts *extracted identifier occurrences*, not distinct names
    and not statements: two references to the same table in one statement are
    two, and a recognised statement with no table position at all (`SELECT 1`)
    contributes nothing to any field. `cte` is structurally unreachable from the
    live scanning path -- see `_d8_table_ref_note` for why that zero is
    disclosed as an unimplemented path rather than as an observation."""
    own: int = 0            # D3.2 state 1 — owned by the importing module
    other: int = 0          # D3.2 state 2 — owned by another module (FAIL)
    cte: int = 0            # D3.2 state 3 — see the note builder: live-unreachable
    system: int = 0         # D3.2 state 4 — reserved system identifier
    external: int = 0       # D3.2 state 5 — declared external_table_references
    unattributed: int = 0   # D3.2 state 6 — anything else (ERROR)

    @property
    def total(self) -> int:
        return (self.own + self.other + self.cte + self.system + self.external
                + self.unattributed)


@dataclass
class _ZeroTableCounts:
    """ADR-011 D6.3 + D8's zero-table triggered-subject partition
    (GATE2-R1-F12-D8-ZERO-TABLE-COUNTER-2026-10-05), mutated in place by
    `_scan_sql_text` for the same reason `_TableRefCounts` is: whatever the run had
    actually established must survive into the ERROR report built by
    `run_module_deps_gate`'s `except GateInputError` handler, labelled a minimum
    rather than discarded with the frame or read as a total.

    Every subject the trigger fired on -- i.e. every statement
    `_scan_sql_statement` returns `True` for, one per lexically certain top-level
    statement cut out of the scanned text by `_d8_statement_subjects`
    (GATE2-R1-F12-D8-STATEMENT-SUBJECTS-2026-10-06) -- increments exactly one of these
    four fields, so the four partition the SQL-trigger count with no overlap and no
    remainder:

      `clean`       D6.3's clean zero-table case: no recognised table position at
                    all **and** no table position implied anywhere in the
                    subject's text (`SELECT 1`, `SELECT now()`, a bare `ANALYZE`, a
                    bare `VACUUM`). A counted, disclosed inspection success.
      `dangling`    refused by ADR-011 D6.7.2's per-position accounting -- at least
                    one recognised table position yielded no identifier to carry to
                    D3.2 attribution, whatever the other positions in the same
                    statement did. ERROR (`MODULE_DEPS_SOURCE_UNINSPECTABLE`).
                    Named `dangling` for continuity with D6.3's original
                    dangling-keyword rule, which this subsumes: a keyword with no
                    identifier after it is one such position.
      `implied`     no recognised table position but a table position *is* implied,
                    so the D6.3 I-1 backstop fires. ERROR
                    (`MODULE_DEPS_SOURCE_UNINSPECTABLE`).
      `with_tables` reduced to at least one identifier, so its references are counted
                    per identifier by `_TableRefCounts` instead of here.

    `dangling` and `implied` are deliberately kept out of `clean` and apart from each
    other. Both are ERROR, so folding either into `clean` would report a fail-closed
    refusal as a clean zero-table success -- the exact over-reassurance this partition
    exists to make impossible -- and collapsing the two into one figure would hide
    which of D6.3's two rules actually fired."""
    clean: int = 0
    dangling: int = 0
    implied: int = 0
    with_tables: int = 0

    @property
    def unresolved(self) -> int:
        """The two ERROR classes together. Derived, never accumulated separately, so
        it cannot drift from the two fields it sums."""
        return self.dangling + self.implied

    @property
    def recognised(self) -> int:
        """Every subject the trigger fired on. By construction this is the figure the
        SQL-trigger counter reports: that counter and these four fields are
        incremented on exactly the same `_scan_sql_statement` paths -- the ones that
        return `True`, which `_scan_sql_text` sums into its own returned count."""
        return self.clean + self.dangling + self.implied + self.with_tables


def _scan_sql_text(text: str, importer: str, modules: Mapping[str, ModuleEntry], loc: str,
                   default_schema: str, violations: list[Violation],
                   uninspectable: list[Violation], unattributed: list[Violation],
                   ref_counts: _TableRefCounts,
                   zero_table: _ZeroTableCounts,
                   suppression: _SuppressionCounts) -> int:
    """One text subject handed to the scanner -- a readable `.sql` file's text, a
    non-docstring `str` literal, or a decoded `bytes` literal -- examined one SQL
    statement at a time.

    GATE2-R1-F12-D8-STATEMENT-SUBJECTS-2026-10-06 (ADR-011 D8): `_d8_statement_subjects`
    cuts `text` at lexically certain top-level `;` boundaries and `_scan_sql_statement`
    below -- unchanged, including its attribution loop and D3.2 precedence -- runs over
    each cut statement in turn. So D8's counters are now literal per-statement
    accounting: `SELECT 1; SELECT now()` is 2 recognised / 2 clean rather than 1/1, and
    `SELECT 1; SELECT id FROM mem_roster` is 2 recognised / 1 clean / 1 table-bearing
    rather than 1/0/1. A semicolon inside a quoted literal, a comment, a dollar-quoted
    body or a double-quoted identifier is not a boundary, and any text whose cut is not
    lexically certain is handed to `_scan_sql_statement` whole -- exactly the single
    coarse subject it was before this increment.

    Returns the number of statements the D6.1 trigger fired on, which is the figure
    `GATE2-R1-F12-D8-SQL-TRIGGER-COUNTER-2026-10-05` discloses and, by construction, the
    sum of the four `zero_table` fields each recognised statement increments. Every
    violation/ERROR still reaches the caller through the three lists exactly as before;
    the return value is disclosure only and says nothing about the verdict. Text the
    trigger never fired on anywhere returns 0 and is never examined, unchanged."""
    if not _is_sql_ish(text):
        return 0
    recognised = 0
    for statement in _d8_statement_subjects(text):
        recognised += int(_scan_sql_statement(
            statement, importer, modules, loc, default_schema, violations,
            uninspectable, unattributed, ref_counts, zero_table, suppression,
        ))
    return recognised


def _scan_sql_statement(text: str, importer: str, modules: Mapping[str, ModuleEntry],
                        loc: str, default_schema: str, violations: list[Violation],
                        uninspectable: list[Violation], unattributed: list[Violation],
                        ref_counts: _TableRefCounts,
                        zero_table: _ZeroTableCounts,
                        suppression: _SuppressionCounts) -> bool:
    """ADR-011 D3.2 (GATE2-R1-D1A-SCANNER-WIRING-2026-10-05): every table-position
    identifier extracted from this one string/file resolves via
    `attribute_table_identifier` to exactly one of six terminal states --

      1/2 (owned by importer / owned by another module) -- `ATTR_OWNED`. Own
          module: clean, no action. Another module: `CROSS_DOMAIN_SQL_IMPORT`.
      3   (CTE-local)              -- `ATTR_CTE`, clean, no action. `cte_names`
          is always the empty default here -- collecting real `WITH ...`
          names lexically is D6 (SQL lexer) work, out of this increment's
          scope, so this state is reachable from `attribute_table_identifier`'s
          own unit tests but not yet from this live scanning path. Disclosed,
          not silently claimed closed.
      4   (reserved system identifier) -- `ATTR_SYSTEM`, clean, no action.
      5   (declared `external_table_references`) -- `ATTR_EXTERNAL`, clean, no
          action.
      6   (anything else)          -- `ATTR_UNATTRIBUTED`, appended to
          `unattributed` as `MODULE_DEPS_TABLE_UNATTRIBUTED` (ERROR). This
          replaces the pre-ADR-011 "unowned ⇒ disclosed note, not flagged"
          behaviour the prior two D1a increments left in place -- an
          unattributed identifier is never again silently passed.

    No identifier falls through without reaching one of the six states above.

    ADR-011 D8 (GATE2-R1-F12-D8-TABLE-STATE-COUNTERS-2026-10-05): each identifier
    that reaches one of those states also increments exactly one field of
    `ref_counts`, in place, so the caller can disclose "table references by D3.2
    state" on PASS, FAIL and ERROR alike. Counting happens where the outcome is
    decided, so a counted reference and a reported violation can never disagree.
    Identifiers this function never extracted are necessarily absent: a subject
    cleared by the D6.3 I-1 backstop or refused by the D6.7.2 per-position
    accounting returns before the loop and contributes zero references, which is
    the truthful figure -- it is disclosed as MODULE_DEPS_SOURCE_UNINSPECTABLE or
    as a recognised-but-table-free statement, not as attributed references.

    ADR-011 D6.7.2 (GATE2-R04-GATE2-R2-N01-D67-EXPLICIT-POSITION-RESULT-CORE-ALIAS-
    LISTS): the accounting seam is `_table_position_results`' per-position stream,
    read once below, and the loop at the bottom ranges over those same records. The
    statement-level `if not idents:` test this replaced asked only whether *any*
    identifier extracted, which cannot establish that every recognised position was
    accounted -- see that call site's own comment.

    ADR-011 D6.3 (GATE2-R1-D6-TRIGGER-I1-2026-10-05): a triggered statement in which
    no table position was recognised at all is handled by the I-1 backstop below,
    immediately after the stream is read -- see its own comment.

    ADR-011 D6.3 + D8 (GATE2-R1-F12-D8-ZERO-TABLE-COUNTER-2026-10-05): each
    recognised subject also increments exactly one field of `zero_table`, in place,
    so the report can disclose how many triggered subjects were *clean with no table
    position at all* (D6.3's clean zero-table case) separately from how many yielded
    no usable identifier and therefore fail closed. The three early returns below are
    the three distinct outcomes, and each is counted on its own return path: the
    D6.7.2 per-position refusal, the I-1 backstop hit, and the clean zero-table case
    that neither of those claims. A fourth field counts the subjects that did reduce
    to at least one identifier, so the four partition the trigger count exactly and
    neither ERROR class can inflate the clean figure.

    Returns whether this one statement was recognised as SQL at all -- i.e. whether
    `_is_sql_ish` fired and the table-position examination below
    therefore ran (GATE2-R1-F12-D8-SQL-TRIGGER-COUNTER-2026-10-05, ADR-011 D8). The
    return value is disclosure only: every violation/ERROR this function can produce
    still reaches the caller through the three lists, exactly as before, and `True`
    says nothing about the verdict -- a triggered subject may be clean, a
    CROSS_DOMAIN_SQL_IMPORT or an ERROR. It is deliberately tied to the trigger and
    not to the three early returns below: text that triggered and then hit the
    D6.7.2 per-position refusal or the D6.3 I-1 backstop *was* recognised and
    examined, so it counts, while text the trigger never fired on was never examined
    at all."""
    if not _is_sql_ish(text):
        return False
    # ADR-011 D6.7.2 (GATE2-R04-GATE2-R2-N01-D67-EXPLICIT-POSITION-RESULT-CORE-ALIAS-
    # LISTS): the accounting seam is the per-position stream, read once here. Every
    # recognised table position in this statement is a record, so the refusal below
    # and the attribution loop at the bottom range over the *same* positions -- the
    # statement-level `if not idents:` test this replaced could not do that. It asked
    # whether *any* identifier extracted, which a statement answers affirmatively
    # while another of its positions goes entirely unaccounted (the documented
    # `FROM mem_roster m, bil_invoices b` false clean at PASS exit 0).
    # ADR-011 D6.8.6: the same single read also folds this statement's privilege-list
    # suppressions into the run-wide sink, so every subject the scanner receives is
    # represented in the D8 disclosure -- including the ones that go on to return
    # early below, since a suppression that happened is disclosed whatever the
    # statement's verdict turns out to be.
    positions = _table_position_results(text, suppression)
    unresolved = [p for p in positions if p.identifier is None]
    if unresolved:
        # ADR-011 D6.7.2: per position, never per statement -- a position that did
        # not yield an identifier carried to D3.2 attribution is ERROR naming that
        # signal, *regardless of how many other positions resolved cleanly*. The
        # refusal therefore fires on `FROM mem_t t, ` (one clean position, one
        # unresolved) exactly as it does on a statement where nothing resolved.
        #
        # ADR-011 D6.3/D8: counted as an *unresolved* zero-table subject, never as a
        # clean one. The signal proves a table position is present; only its name is
        # unreachable, so this is the opposite claim from `SELECT 1`.
        zero_table.dangling += 1
        uninspectable.append(Violation(
            "MODULE_DEPS_SOURCE_UNINSPECTABLE", loc,
            "SQL-ish text has a recognised table position not followed by an "
            "identifier, so it could not be carried to ADR-011 D3.2 attribution "
            "(D6.7.2, per position, regardless of how many other positions in the "
            "same statement resolved cleanly): "
            + "; ".join(p.describe() for p in unresolved),
        ))
        return True
    if not positions:
        # ADR-011 D6.3: the corrected I-1 backstop. Reached only when *no* table
        # position was recognised at all -- not merely when no identifier extracted,
        # which is the weaker statement the replaced `if not idents:` made. With the
        # refusal above having returned on any unresolved position, an empty stream
        # here is the honest claim "this statement has no recognised table position",
        # so the clean/implied split below is decided on the same ground it always
        # was: zero recognised positions is ERROR only when the text nonetheless
        # carries a table-position keyword (the broader ONLY/REFERENCES-inclusive
        # `_TABLE_POSITION_KEYWORD_RE`, not just what the extractor above can
        # resolve) or a bare-table verb form -- both mean a real table reference the
        # extractor could not
        # resolve, so this fails closed rather than silently passing. A triggered
        # statement with no table position at all -- `SELECT 1`, `SELECT now()`, a
        # bare `ANALYZE`, a bare `VACUUM` -- is clean and counted/disclosed
        # normally: an unqualified "triggered but zero refs => ERROR" rule would
        # flag the most common operational SQL in existence.
        #
        # ADR-011 D6.3/D8 (GATE2-R1-F12-D8-ZERO-TABLE-COUNTER-2026-10-05): the two
        # branches below are counted under *separate* fields, decided on the same line
        # of control flow that already decided the outcome. The backstop hit is an
        # unresolved subject at exit 2; only the `else` is D6.3's clean zero-table
        # success. Counting them together would let a fail-closed refusal read as
        # evidence of a clean, examined, table-free statement.
        if _implies_table_position(text):
            zero_table.implied += 1
            uninspectable.append(Violation(
                "MODULE_DEPS_SOURCE_UNINSPECTABLE", loc,
                "SQL-ish text implies a table position (a table-position keyword or "
                "a bare-table verb form is present) but no identifier could be "
                "extracted (ADR-011 D6.3 I-1 backstop)",
            ))
        else:
            zero_table.clean += 1
        return True
    # ADR-011 D6.3/D8: this subject reduced to at least one identifier, so it is the
    # fourth, table-bearing member of the partition -- its references are counted per
    # identifier in `ref_counts` by the loop below, never in the zero-table fields.
    # Incremented before the loop so a subject counts as table-bearing on exactly the
    # condition that made it one (`positions` non-empty), independent of which states
    # those identifiers go on to reach.
    zero_table.with_tables += 1
    # ADR-011 D6.7.2: the loop ranges over the recognised *positions*, not over a
    # separately-built identifier list that could be shorter than them. That is the
    # accounting comparison, made structurally rather than numerically: every
    # recognised position is driven to exactly one D3.2 terminal state here, and
    # there is no intermediate collection in which one could be dropped silently.
    for position in positions:
        ident = position.identifier
        if ident is None:
            # Unreachable: the D6.7.2 refusal above returns on any unresolved
            # position. Fail closed rather than skip, so a future edit that moves or
            # weakens that refusal surfaces at exit 2 through D7.3's outermost funnel
            # instead of silently resuming the "drop what did not resolve" behaviour
            # this increment removed.
            raise ValueError(
                f"ADR-011 D6.7.2: unresolved table position reached attribution at "
                f"{loc}: {position.describe()}"
            )
        outcome = attribute_table_identifier(ident, modules, importer, default_schema)
        # ADR-011 D8 (GATE2-R1-F12-D8-TABLE-STATE-COUNTERS-2026-10-05): every branch
        # below increments exactly one counter, on the same line of control flow that
        # already decided the outcome -- so the disclosed counts can only ever be the
        # states this scan really produced, never a separate re-derivation that could
        # disagree with the violations in the same report. The counters are disclosure
        # only: no verdict, code, exit status or violation text changes here.
        if outcome.state == ATTR_OWNED:
            if outcome.owner != importer:
                ref_counts.other += 1          # D3.2 state 2
                violations.append(Violation(
                    "CROSS_DOMAIN_SQL_IMPORT", f"{importer} -> {outcome.owner}",
                    f"{loc}: table {ident!r} owned by {outcome.owner!r}",
                ))
            else:
                ref_counts.own += 1            # D3.2 state 1
        elif outcome.state == ATTR_UNATTRIBUTED:
            ref_counts.unattributed += 1       # D3.2 state 6
            unattributed.append(Violation(
                "MODULE_DEPS_TABLE_UNATTRIBUTED", loc,
                f"table {ident!r}: {outcome.reason}",
            ))
        # ATTR_CTE / ATTR_SYSTEM / ATTR_EXTERNAL (states 3/4/5): clean, no action
        # beyond being counted. ATTR_CTE is unreachable from here by construction --
        # `attribute_table_identifier` is called above with its default empty
        # `cte_names`, and wiring `_collect_cte_names` in is held FORBIDDEN by the
        # qualified U1/U2 B HOLD -- so `ref_counts.cte` stays a genuine zero rather
        # than being connected to make the field look exercised.
        elif outcome.state == ATTR_CTE:
            ref_counts.cte += 1                # D3.2 state 3 — live-unreachable
        elif outcome.state == ATTR_SYSTEM:
            ref_counts.system += 1             # D3.2 state 4
        elif outcome.state == ATTR_EXTERNAL:
            ref_counts.external += 1           # D3.2 state 5
        else:
            # Fail-closed, not a fallthrough: D3.2 names exactly six terminal states
            # and `AttributionOutcome.state` is one of the five ATTR_* constants. An
            # unrecognised state means a seventh was introduced without a counter, and
            # an uncounted reference would silently under-disclose. This surfaces
            # through D7.3's outermost funnel at exit 2 instead.
            raise ValueError(
                f"unknown ADR-011 D3.2 attribution state {outcome.state!r} for "
                f"identifier {ident!r} at {loc}"
            )
    return True


# --- ADR-011 D3.2 state 3: pure lexical CTE-name collection (increment D6a) -----
#
# GATE2-R1-D6-CTE-HELPER-2026-10-05: `_collect_cte_names` is a standalone, pure,
# lexical-only helper implementing the depth-0 half of ADR-011 D3.2 state 3
# ("Bound locally in the same statement (a `WITH` CTE name, collected lexically
# at depth 0)"). It is deliberately NOT wired into `_scan_sql_text` above by this
# increment -- the live scanning path still calls `attribute_table_identifier`
# with its default empty `cte_names`, exactly as `_scan_sql_text`'s own comment
# already discloses ("`cte_names` is always the empty default here ... this
# state is reachable from `attribute_table_identifier`'s own unit tests but not
# yet from this live scanning path"). That remains true after this increment;
# wiring this helper in is separate, future work.
_CTE_WITH_RE = re.compile(r"\bWITH\b", re.IGNORECASE)
_CTE_AS_RE = re.compile(r"\bAS\b", re.IGNORECASE)
_CTE_WS_RE = re.compile(r"\s*")

# --- GATE2-R1-D6-CTE-LEXICAL-HARDENING-2026-10-05 -------------------------------
#
# The increment above disclosed a real gap: this module has no single-quoted
# SQL string-literal lexer or SQL-comment lexer anywhere, so deceptive text
# such as `WITH fake AS (` inside a `'...'` literal or a `-- `/`/* */` comment
# could create a false CTE binding and/or corrupt paren-depth tracking. The
# three helpers below close that gap for `_collect_cte_names` and
# `_skip_balanced_parens` specifically; they do not touch `_scan_sql_text` or
# any other caller, and `_collect_cte_names` remains unwired (see above).
_LINE_COMMENT_START_RE = re.compile(r"--")
_BLOCK_COMMENT_OPEN_RE = re.compile(r"/\*")
_BLOCK_COMMENT_BOUNDARY_RE = re.compile(r"/\*|\*/")

# --- GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05 -------------------------------
#
# The increment above disclosed a further real gap, explicitly out of its own
# scope: this module had no PostgreSQL dollar-quoted-string (`$$...$$` /
# `$tag$...$tag$`) lexer, so deceptive `WITH fake AS (` text inside one could
# still create a false CTE binding and/or corrupt paren-depth tracking. The
# helper below closes that gap for `_collect_cte_names` and
# `_skip_balanced_parens` specifically, via the same `_skip_quote_or_comment`
# dispatcher both already call; it does not touch `_scan_sql_text` or any
# other caller, and `_collect_cte_names` remains unwired (see the module-level
# comment above).
#
# GATE2-R1-D6-CTE-UNICODE-DOLLAR-2026-10-05: the original increment above
# recognised only an ASCII-only tag (reusing this module's `_BARE_IDENT_RE`,
# `[A-Za-z_][A-Za-z0-9_]*`) and its own residual-risk disclosure characterised
# an unrecognised non-ASCII tag as "safe-direction only" -- that
# characterisation was WRONG and is corrected here, not merely re-asserted:
# a dollar-quote opener that goes unrecognised does not degrade to a missed
# *binding*, it degrades to the entire dollar-quoted region being scanned as
# ORDINARY TOP-LEVEL TEXT -- so a `WITH fake AS (...)` sitting inside an
# unrecognised `$café$...$café$` region is read as a real, depth-0 CTE
# binding and collected. Proven live:
# `_collect_cte_names("SELECT $café$ WITH fake AS (SELECT 1) $café$")`
# returned `frozenset({"fake"})` before this increment -- a FALSE binding,
# the unsafe direction `_collect_cte_names`'s own docstring says this
# function must never produce. See `GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05.md`'s
# "Orchestrator correction" section and
# `GATE2-R1-D6-CTE-UNICODE-DOLLAR-2026-10-05.md` for the full record.
#
# Fixed by recognising the tag using PostgreSQL's REAL identifier rules
# (https://www.postgresql.org/docs/current/sql-syntax-lexical.html): an
# unquoted identifier's first character may be "a letter (including letters
# with diacritical marks and non-Latin letters) or an underscore", and
# continuation characters may additionally be digits, approximated here with
# Python's Unicode-aware `str.isalpha()` ("letter") and `str.isalnum()`
# ("letter or digit") -- deliberately NOT `_BARE_IDENT_RE`, which is
# ASCII-only and exists for this module's ordinary bare-identifier use,
# unrelated to the dollar-quote tag rule. A tag may never contain `$`
# (PostgreSQL's own stated exception to the identifier rule), which is
# satisfied by construction since `$` is never a letter/digit/underscore. A
# digit immediately after the opening `$` (e.g. `$1`, a positional parameter)
# can never start a tag, so it is correctly never misread as an opener.
# Matching is exact substring/case-sensitive (`str.find`), per PostgreSQL's
# own rule that the tag "is case-sensitive" and the closing delimiter "must
# have exactly the same tag". An empty tag (`$$...$$`) remains valid.


def _skip_single_quoted_literal(text: str, pos: int) -> int | None:
    """`text[pos]` must be `"'"`. Returns the index immediately after the
    literal's closing `'`, or `None` if `text` ends before one is found (an
    unterminated literal, which simply consumes the rest of `text` -- callers
    must stop scanning entirely, never guess a close).

    Two escape shapes are recognised, both treated as "this `'` does not
    close the literal":
    - SQL's own doubled-quote escape (`''`, one literal `'` character).
    - A backslash immediately before any character, including a `'`. This is
      PostgreSQL `E'...'`-escape-string syntax (`\\'`), but it is applied here
      to every single-quoted literal, not only ones with a leading `E` --
      this function does not look behind `pos` to check for one. That is a
      deliberate, fail-closed simplification: treating a backslash-adjacent
      quote as non-closing can only make this function consume MORE of
      `text` as "inside the literal" than a real Postgres lexer would for a
      non-`E` string (never less), which can only cause a real binding to be
      missed (ADR-011 D3.2 state 3's already-safe direction -- see
      `_collect_cte_names`'s docstring) -- it can never manufacture a false
      binding by closing early. It never mis-closes early in the other
      direction either, which an `E`-string-unaware doubled-quote-only lexer
      would: `E'foo\\' WITH fake AS ('` would otherwise read the backslash-
      escaped quote as a real closing quote, exposing the attacker's text as
      ordinary SQL one token later -- the literal false-binding risk this
      increment exists to close. See this function's module-level residual
      note on `E`-strings for what is still NOT handled (non-`\\'`/`\\\\`
      backslash escape *meanings*, e.g. `\\n`, are irrelevant here since this
      function only ever looks at the single character right after a
      backslash, never interprets it)."""
    assert text[pos] == "'"
    i = pos + 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "'":
            if i + 1 < n and text[i + 1] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    return None


def _skip_line_comment(text: str, pos: int) -> int:
    """`text[pos:pos + 2]` must be `"--"`. Returns the index immediately after
    the line's terminating `\\n`, or `len(text)` if the comment runs to the
    end of input -- a line comment is always well-formed; running to end of
    input is its own defined closing boundary, never a failure."""
    assert text[pos:pos + 2] == "--"
    nl = text.find("\n", pos + 2)
    return len(text) if nl == -1 else nl + 1


def _skip_block_comment(text: str, pos: int) -> int | None:
    """`text[pos:pos + 2]` must be `"/*"`. Returns the index immediately after
    the matching `*/`, or `None` if `text` ends before one is found (an
    unterminated block comment, which consumes the rest of `text` -- callers
    must stop scanning entirely).

    PostgreSQL block comments nest (confirmed against the live PostgreSQL
    documentation, "SQL Syntax" / lexical-structure chapter: "these block
    comments nest, as specified in the SQL standard but unlike C" -- unlike a
    C-style `/* */` comment, a `/* /* */ */` is one single comment, not a
    comment immediately followed by stray text). A nested `/*` increments a
    depth counter; only the `*/` that brings depth back to 0 closes the
    outer comment."""
    assert text[pos:pos + 2] == "/*"
    depth = 1
    i = pos + 2
    n = len(text)
    while i < n:
        boundary = _BLOCK_COMMENT_BOUNDARY_RE.match(text, i)
        if boundary is None:
            i += 1
            continue
        if boundary.group(0) == "/*":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return boundary.end()
        i = boundary.end()
    return None


def _is_dolq_start(ch: str) -> bool:
    """Mirrors scan.l's `dolq_start [A-Za-z\\200-\\377_]` byte class."""
    return ch == "_" or "a" <= ch <= "z" or "A" <= ch <= "Z" or ord(ch) >= 0x80


def _is_dolq_cont(ch: str) -> bool:
    """Mirrors scan.l's `dolq_cont [A-Za-z\\200-\\377_0-9]` byte class."""
    return _is_dolq_start(ch) or "0" <= ch <= "9"


def _match_dollar_quote_opener(text: str, pos: int) -> int | None:
    """`text[pos]` must be `"$"`. If a PostgreSQL dollar-quote opening
    delimiter (`$$` or `$tag$`) starts exactly here, returns the index
    immediately after the full opening delimiter (so `text[pos:result]` is
    e.g. `"$$"` or `"$tag$"`). Returns `None` if no valid opener starts
    here at all -- including a positional parameter (`$1`, `$23`, ...), a
    bare `$`, or ordinary currency/dollar text; the caller must treat `$` as
    an ordinary character in that case, never guess an opener.

    GATE2-R1-D6-CTE-HIGHBIT-DOLLAR-2026-10-05: the tag is matched against
    PostgreSQL's ACTUAL byte lexer, `src/backend/parser/scan.l`
    (https://github.com/postgres/postgres/blob/master/src/backend/parser/scan.l),
    whose relevant classes are `dolq_start [A-Za-z\\200-\\377_]` and
    `dolq_cont [A-Za-z\\200-\\377_0-9]` -- not this module's ASCII-only
    `_BARE_IDENT_RE`, and not a character-category approximation such as
    `str.isalpha()`/`str.isalnum()`. Because every well-formed non-ASCII
    UTF-8 codepoint encodes to a leading byte in `\\200-\\377`, PostgreSQL's
    `dolq_start` accepts ANY non-ASCII codepoint as a tag start -- a bare
    Unicode combining mark (e.g. U+0301 COMBINING ACUTE ACCENT), an emoji,
    and a C1 control character (e.g. U+0085, which encodes as UTF-8 `C2
    85`) all start a tag just as validly as an ASCII letter does. There is
    no "continuation-only" rule for combining marks or any other non-ASCII
    codepoint; the previous `str.isalpha()`/`str.isalnum()` plus
    `Mn`/`Mc`/`Me` category approximation was wrong in the UNSAFE
    direction -- it manufactured false CTE bindings by misdetecting valid
    openers as absent and letting the dollar-quoted body leak into the
    ordinary top-level scan, rather than merely missing a binding.

    What still cannot start a tag: an ASCII digit (identifiers never start
    with a digit, so `$1`/`$23`/etc. always fail to match here and are
    correctly left for the caller as positional parameters, not openers),
    and any other ASCII control or punctuation byte (below `0x80` and
    outside `[A-Za-z_]`). ASCII digits may only CONTINUE a tag, never start
    one. `$` (`0x24`) itself is in neither `dolq_start` nor `dolq_cont`, so
    a tag can never contain one, satisfying PostgreSQL's stated exception
    without any extra exclusion check. An empty tag (`$$`) is checked first
    and is always valid.

    The body itself is still skipped atomically by `_skip_dollar_quoted_string`
    via a byte-exact literal match of the opening delimiter text, with no
    Unicode normalisation -- so a decomposed-tag opener is still only closed
    by the identical decomposed byte sequence, never by a canonically
    equivalent precomposed look-alike."""
    assert text[pos] == "$"
    n = len(text)
    i = pos + 1
    if i < n and text[i] == "$":
        return i + 1
    if i < n and _is_dolq_start(text[i]):
        i += 1
        while i < n and _is_dolq_cont(text[i]):
            i += 1
        if i < n and text[i] == "$":
            return i + 1
    return None


def _skip_dollar_quoted_string(text: str, pos: int, opener_end: int) -> int | None:
    """`text[pos]` must be `"$"` and `opener_end` must be the result of a
    successful `_match_dollar_quote_opener(text, pos)` call -- so
    `text[pos:opener_end]` is the exact opening delimiter (`$$` or `$tag$`).
    Returns the index immediately after the matching closing delimiter --
    found via a plain, literal, case-sensitive substring search for that
    exact same delimiter text, never regenerated or guessed, matching
    PostgreSQL's own rule that the closing tag must be byte-for-byte
    identical to the opening one -- or `None` if `text` ends before it is
    found (an unterminated dollar-quoted string, which consumes the rest of
    `text` -- callers must stop scanning entirely, the same fail-closed
    convention every other lexical region in this module already uses). The
    entire body between the delimiters is skipped atomically by this one
    `str.find` call -- no tokenizing, no paren counting, and no `WITH`
    recognition ever happens on any text inside it."""
    delim = text[pos:opener_end]
    close = text.find(delim, opener_end)
    return None if close == -1 else close + len(delim)


def _skip_quote_or_comment(text: str, pos: int) -> int | None:
    """If a single-quoted string literal, a `--` line comment, a `/* */`
    block comment, or a dollar-quoted string (`$$...$$` / `$tag$...$tag$`)
    starts exactly at `text[pos]`, returns the index immediately after it. If
    none of those four shapes starts at `pos`, returns `pos` unchanged
    (nothing for the caller to skip here) -- this includes a bare `$` that is
    not a valid dollar-quote opener at all (a positional parameter like `$1`,
    or ordinary currency/dollar text), which is left for the caller to treat
    as an ordinary character, exactly as before this helper existed. An
    unterminated literal, block comment, or dollar-quoted string returns
    `None` -- the caller must stop scanning entirely in that case (the same
    fail-closed convention `_lex_quoted_segment` already uses for an
    unterminated double-quoted segment); a line comment never returns `None`,
    since running to end of input is itself its well-defined closing
    boundary. Double-quoted identifiers are NOT this function's concern --
    both call sites below already check for `'"'` themselves, via the
    pre-existing `_lex_quoted_segment`, before ever reaching this
    dispatcher."""
    if text[pos] == "'":
        return _skip_single_quoted_literal(text, pos)
    if _LINE_COMMENT_START_RE.match(text, pos):
        return _skip_line_comment(text, pos)
    if _BLOCK_COMMENT_OPEN_RE.match(text, pos):
        return _skip_block_comment(text, pos)
    if text[pos] == "$":
        opener_end = _match_dollar_quote_opener(text, pos)
        if opener_end is not None:
            return _skip_dollar_quoted_string(text, pos, opener_end)
    return pos


def _skip_balanced_parens(text: str, pos: int) -> int | None:
    """`text[pos]` must be `"("`. Returns the index immediately after its
    matching `")"`, skipping any nested parens, any double-quoted segment
    (via `_lex_quoted_segment`, so a paren character written inside a quoted
    identifier is never mistaken for a real one), any single-quoted string
    literal or SQL comment (GATE2-R1-D6-CTE-LEXICAL-HARDENING-2026-10-05),
    and any dollar-quoted string (GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05) --
    all three via `_skip_quote_or_comment`, so a paren character written
    inside a literal, comment, or dollar-quoted string never shifts depth
    either -- along the way. Returns `None` if the text ends before the
    matching `")"` is found, or before an opened literal/comment/dollar-quote
    inside the body closes -- an unbalanced, unlexable body, never guessed
    closed."""
    assert text[pos] == "("
    depth = 1
    i = pos + 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            lexed = _lex_quoted_segment(text, i)
            if lexed is None:
                return None
            _, i = lexed
            continue
        skipped = _skip_quote_or_comment(text, i)
        if skipped is None:
            return None
        if skipped != i:
            i = skipped
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _parse_one_cte_binding(text: str, pos: int) -> tuple[str, int] | None:
    """Starting exactly at `pos` (no leading whitespace), lexes one `name AS (`
    binding -- a quoted or bare name, ADR-011 D3.1 normalisation applied via
    the same `_normalize_identifier_segment` the live attribution path uses.
    Returns `(normalised_name, index_of_opening_paren)`, or `None` if `pos`
    does not lexically start a binding of exactly this shape.

    Deliberately does not recognise `RECURSIVE`, a parenthesised column-name
    list after the name (`WITH cte(a, b) AS (...)`), or `[NOT] MATERIALIZED`
    -- any of those makes this binding fail closed (`None`) rather than being
    guessed past. See `_collect_cte_names`'s LIMITATIONS note."""
    seg = _lex_identifier_segment(text, pos)
    if seg is None:
        return None
    raw_name, end = seg
    pos2 = _CTE_WS_RE.match(text, end).end()
    as_match = _CTE_AS_RE.match(text, pos2)
    if as_match is None:
        return None
    pos3 = _CTE_WS_RE.match(text, as_match.end()).end()
    if pos3 >= len(text) or text[pos3] != "(":
        return None
    return _normalize_identifier_segment(raw_name), pos3


def _parse_cte_binding_list(text: str, pos: int) -> tuple[frozenset[str], int]:
    """Starting exactly at `pos` (immediately after the `WITH` keyword and any
    whitespace -- the caller has already skipped both), parses a comma-
    separated list of CTE bindings for as long as each one lexically confirms
    as `name AS (...)`. Returns the bound names and the index immediately
    after the list (the last body's closing `)`), or `(frozenset(), pos)`
    unchanged if not even one binding confirmed.

    Stops -- without consuming anything past the last confirmed binding -- the
    moment a binding fails to confirm or a body's parens are unbalanced; every
    name already collected by that point was independently confirmed on its
    own and is kept (ADR-011 D3.2 state 3 is a per-binding decision, not an
    all-or-nothing one for the whole list)."""
    names: set[str] = set()
    cur = pos
    while True:
        binding = _parse_one_cte_binding(text, cur)
        if binding is None:
            break
        name, open_paren = binding
        end = _skip_balanced_parens(text, open_paren)
        if end is None:
            break
        names.add(name)
        after_ws = _CTE_WS_RE.match(text, end).end()
        if after_ws < len(text) and text[after_ws] == ",":
            cur = _CTE_WS_RE.match(text, after_ws + 1).end()
            continue
        cur = after_ws
        break
    return frozenset(names), cur


def _collect_cte_names(text: str) -> frozenset[str]:
    """ADR-011 D3.2 state 3: every CTE name bound by a `WITH` clause at
    parenthesis depth 0 of `text`, collected purely lexically -- no SQL
    parser, no I/O, no mutation of `text`.

    Depth is tracked across the whole string, skipping double-quoted segments
    via `_lex_quoted_segment` -- and, GATE2-R1-D6-CTE-LEXICAL-HARDENING-
    2026-10-05, single-quoted string literals and SQL line/block comments,
    plus, GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05, dollar-quoted strings
    (`$$...$$` / `$tag$...$tag$`) -- all via `_skip_quote_or_comment` -- so a
    paren character, or the text `WITH` itself, written inside any of those
    five lexical regions never corrupts depth or creates a binding. A `WITH`
    keyword is only ever inspected as a binding-list opener when depth is
    exactly 0 at its start AND it is not inside a quoted/commented/dollar-
    quoted region -- a `WITH` nested inside any parenthesised subquery or CTE
    body is at depth >= 1 and is never inspected at all, so neither its own
    bindings nor anything that merely looks like one can leak into the
    depth-0 result.

    Fails closed on ambiguity, always: a `WITH` whose binding list cannot be
    lexed cleanly from its very first token (no identifier, no `AS`, no
    following `(`, an unbalanced body) collects no name for that position at
    all -- scanning simply resumes past the `WITH` keyword as ordinary text.
    An unterminated single-quoted literal, unterminated block comment, or
    unterminated dollar-quoted string anywhere in `text` stops scanning
    entirely at that point (mirroring the pre-existing unterminated-double-
    quote behaviour) -- everything already collected up to then is kept,
    nothing past it is ever inspected. A
    missed binding (for any of these reasons) degrades to ADR-011 D3.2 state
    6 (`MODULE_DEPS_TABLE_UNATTRIBUTED`, an ERROR) -- the safe direction; a
    false binding would silently clean a real cross-domain import, the unsafe
    direction. This function never guesses the latter.

    LIMITATIONS (disclosed, not silently covered):
    - `RECURSIVE`, a parenthesised column-name list after a CTE name (`WITH
      cte(a, b) AS (...)`), and `[NOT] MATERIALIZED` are not recognised --
      any of them makes `_parse_one_cte_binding` fail closed for that binding
      (no name collected), never guessed past.
    - Dollar-quoted strings (`$$...$$`, `$tag$...$tag$`) are recognised and
      skipped atomically, GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05 (see
      `_skip_dollar_quoted_string`) -- the opening and closing delimiters
      must match exactly (same tag, found via a literal, case-sensitive
      substring search, never regenerated or guessed); an unterminated or
      mismatched-tag opener fails closed exactly like an unterminated
      single-quoted literal. GATE2-R1-D6-CTE-UNICODE-DOLLAR-2026-10-05: the
      tag's character set follows PostgreSQL's REAL identifier rules (see
      `_match_dollar_quote_opener`) -- Unicode letters/digits/underscore, not
      starting with a digit -- NOT this module's ASCII-only `_BARE_IDENT_RE`,
      so a non-ASCII tag (e.g. `$café$`) is correctly recognised and skipped
      atomically, not left as ordinary text. This corrects a prior
      (GATE2-R1-D6-CTE-DOLLAR-QUOTE-2026-10-05) residual-risk claim that an
      unrecognised non-ASCII tag was "safe-direction only" -- it was not: an
      unrecognised opener does not degrade to a missed *binding*, it degrades
      to the whole dollar-quoted region being scanned as ordinary top-level
      text, so a `WITH fake AS (...)` inside it was collected as a FALSE
      binding (proven live pre-fix:
      `_collect_cte_names("SELECT $café$ WITH fake AS (SELECT 1) $café$")`
      returned `frozenset({"fake"})`). A positional parameter (`$1`, `$2`,
      ...) or ordinary currency/dollar text is never mistaken for an opening
      delimiter, since a digit can never start a tag.
    - `E'...'`-escape-string semantics are only partially covered:
      `_skip_single_quoted_literal` treats a backslash as escaping the next
      character for every single-quoted literal (not only ones with a
      leading `E`), which closes the one false-binding risk a backslash-
      naive scanner would have (`E'foo\\' WITH fake AS ('` no longer closes
      early) -- but it does not interpret the escape's *meaning*
      (`\\n`/`\\xNN`/`\\uNNNN`/etc.), because no part of this function's
      output depends on a literal's decoded value, only on where it ends.
    - Unicode identifier escapes (`U&"..."` / `U&'...'`) are not recognised
      as a distinct shape; a `U&"..."` double-quoted form is lexed as an
      ordinary double-quoted segment by the pre-existing `_lex_quoted_segment`
      (its content, not its `U&` prefix, is what `_collect_cte_names` sees),
      and a `U&'...'` single-quoted form is lexed as an ordinary
      single-quoted literal by `_skip_single_quoted_literal` above -- both
      close correctly at the real terminating quote in the common case, but
      neither path validates or specially handles a `UESCAPE` clause
      trailing the literal.
    - Double-quoted identifiers (including one with an escaped embedded `"`)
      are already handled, via the pre-existing `_lex_quoted_segment` --
      unchanged by this increment.
    - Not wired into `_scan_sql_text`; see the comment at the top of this
      section.
    """
    names: set[str] = set()
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            lexed = _lex_quoted_segment(text, i)
            if lexed is None:
                break
            _, i = lexed
            continue
        skipped = _skip_quote_or_comment(text, i)
        if skipped is None:
            break
        if skipped != i:
            i = skipped
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0:
            with_match = _CTE_WITH_RE.match(text, i)
            if with_match is not None:
                cur = _CTE_WS_RE.match(text, with_match.end()).end()
                found, end = _parse_cte_binding_list(text, cur)
                names.update(found)
                i = end
                continue
        i += 1
    return frozenset(names)


# --- GATE2-R1-D6-ONE-PASS-CTE-SCOPES-2026-10-05 ---------------------------------
#
# `_cte_scopes` is the smallest next legal subgoal named by
# `GATE2-R1-D6-CTE-STATEMENT-SCOPE-LEAD-QUALIFICATION-2026-10-05.md` section
# 2(b)(1), after the named `veyro-lead` BLOCKED the two-function
# `_split_sql_statements` + reused-`_collect_cte_names` design: that design's
# Lemma L ("the two walks share the same dispatch") was false against this
# source -- the designed splitter had no `WITH` branch at all (so it could
# never share `_collect_cte_names`'s `WITH` -> `_parse_cte_binding_list`
# cursor jump), and `_collect_cte_names` has no depth-0 `;`-cut branch the
# splitter needed. `_cte_scopes` below collapses both branches into ONE
# lexical cursor, so there is only one walk and Lemma L becomes vacuous by
# construction: there is nothing left for two dispatches to disagree about.
#
# Deliberately NOT wired into `_scan_sql_text` or any other call site -- see
# the module-level comment above `_collect_cte_names`. `_scan_sql_text` keeps
# calling `attribute_table_identifier` with its default empty `cte_names`,
# unchanged by this increment; D3.2 state 3 remains unreachable from the live
# scanning path.
def _cte_scopes(text: str) -> list[tuple[str, frozenset[str]]]:
    """ADR-011 D3.2 state 3, statement-scoped, in one pass: emits
    `(segment_text, frozenset(cte_names))` pairs, one per lexically
    delimited statement in `text`, via a single lexical cursor / dispatch
    loop -- no `_split_sql_statements`, and no second walk over any segment
    via `_collect_cte_names`. Every binding comes from this one pass.

    The dispatch, at every position, in this fixed order:

    1. `text[i] == '"'` -> `_lex_quoted_segment`. `None` (an unterminated
       double-quoted identifier) -> decline the WHOLE text (see below).
    2. Otherwise `_skip_quote_or_comment` (single-quoted literal, `--` line
       comment, `/* */` block comment, dollar-quoted string). `None` (any
       of those left unterminated) -> decline the whole text. A returned
       index `!= i` means the region was skipped atomically; nothing
       inside it is ever inspected, exactly as `_collect_cte_names` and
       `_skip_balanced_parens` already behave.
    3. `(` increments a depth counter; `)` decrements it with
       `max(0, depth - 1)` -- the same floor `_collect_cte_names` already
       uses, so an excess `)` can never drive depth negative.
    4. `;` **at depth == 0**: closes the current segment at
       `text[start:i]` (the `;` itself is excluded from both the closed
       segment and the next one) and starts the next segment, with its own
       fresh, empty binding accumulator, at `i + 1`.
    5. Otherwise, **at depth == 0 only**: a `WITH` keyword is recognised
       exactly as `_collect_cte_names` already recognises it -- whitespace
       is skipped and the existing `_parse_cte_binding_list` is called,
       reusing its cursor jump verbatim (`i = end`). The entire
       `name AS (...)` binding list -- including any nested parens,
       quotes, comments, or dollar-quoted bodies in its own body -- is
       consumed atomically by that pre-existing helper's own
       `_skip_balanced_parens` calls, never re-walked here. Confirmed
       names are added to the *current segment's* accumulator only --
       there is no later, separate collection pass for them to leak into.
    6. Any other character, at any depth: advance one position.

    After the loop, the final `text[start:]` is closed out as the last
    segment, under the same decline rule as every other segment.

    Per-segment decline (the trust predicate -- applied to the FINAL
    sliced segment text, not to characters visited mid-scan): a segment
    whose sliced text contains ANY `;` character at all has its bindings
    declined to `frozenset()`, discarding whatever this pass collected for
    it. A depth-0 `;` outside every lexical region is always consumed as a
    cut and excluded from both neighbours (step 4), so the only way a `;`
    can still be present in a segment's sliced text is if it was inside a
    lexical region skipped atomically in step 1/2 (a literal, a comment, a
    dollar-quoted body, a double-quoted identifier) or inside parentheses
    at depth > 0 -- exactly the cases where this segment's own boundaries,
    or its interior, were not established purely by top-level structure.
    This is ADR-011 D3.2 state 3's fail-closed half: declining can only
    remove the state-3 branch for an identifier, sending it through the
    unchanged D3.2 precedence chain -- it can never manufacture a false
    clean state.

    Whole-text decline, `[(text, frozenset())]`: raised the moment step 1
    or step 2 returns `None` anywhere in `text` -- an unterminated
    double-quoted identifier, single-quoted literal, block comment, or
    dollar-quoted string. Lexical segmentation is impossible past that
    point, so nothing already scanned is trusted either; the whole text is
    handed back as one declined scope rather than guessing a boundary.

    This function performs no I/O and mutates no argument."""
    scopes: list[tuple[str, frozenset[str]]] = []
    depth = 0
    start = 0
    names: set[str] = set()
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            lexed = _lex_quoted_segment(text, i)
            if lexed is None:
                return [(text, frozenset())]
            _, i = lexed
            continue
        skipped = _skip_quote_or_comment(text, i)
        if skipped is None:
            return [(text, frozenset())]
        if skipped != i:
            i = skipped
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0 and ch == ";":
            segment_text = text[start:i]
            scopes.append((
                segment_text,
                frozenset() if ";" in segment_text else frozenset(names),
            ))
            start = i + 1
            names = set()
            i += 1
            continue
        if depth == 0:
            with_match = _CTE_WITH_RE.match(text, i)
            if with_match is not None:
                cur = _CTE_WS_RE.match(text, with_match.end()).end()
                found, end = _parse_cte_binding_list(text, cur)
                names.update(found)
                i = end
                continue
        i += 1
    segment_text = text[start:]
    scopes.append((
        segment_text,
        frozenset() if ";" in segment_text else frozenset(names),
    ))
    return scopes


# --- GATE2-R1-F12-D8-STATEMENT-SUBJECTS-2026-10-06: ADR-011 D8 statement accounting -
#
# The one helper below is wired into `_scan_sql_text` so ADR-011 D8's SQL-trigger count
# and D6.3/D8 zero-table partition become literal per-STATEMENT accounting instead of
# per-text-blob accounting. Before this increment the whole of one readable `.sql` file
# was a single subject, so `SELECT 1; SELECT now()` reported 1 recognised / 1 clean
# rather than 2/2, and `SELECT 1; SELECT id FROM mem_roster` reported 1 recognised /
# 0 clean / 1 table-bearing rather than 2/1/1 -- which is exactly what the zero-table
# note disclosed as its LIMIT.
#
# It reuses the existing lexical dispatch -- `_lex_quoted_segment` for a double-quoted
# identifier and `_skip_quote_or_comment` for a single-quoted literal, a `--` line
# comment, a `/* */` block comment and a `$$`/`$tag$` dollar-quoted body -- rather than
# cutting on `";"` textually, so a semicolon written inside any of those regions, or
# inside parentheses, is never mistaken for a statement boundary.
#
# This is NOT the CTE wiring held FORBIDDEN by the qualified U1/U2 B HOLD: it never
# calls `_cte_scopes`, never collects or passes `cte_names`, and has no `WITH` branch at
# all. D3.2 state 3 stays unreachable from the live scanning path and `ref_counts.cte`
# stays a genuine zero. Attribution precedence and `_scan_sql_statement`'s attribution
# loop are untouched -- this helper only decides how the text is divided before that
# unchanged loop runs over each piece.
def _d8_statement_subjects(text: str) -> list[str]:
    """The segments of `text` the D6.1 trigger fires on, cut at lexically certain
    top-level `;` boundaries -- or `[text]` unchanged when the cut cannot be
    established lexically (the fail-closed decline below).

    The dispatch, at every position, in this fixed order -- deliberately the same
    order and the same helpers `_cte_scopes` and `_skip_balanced_parens` already use,
    so a region either of them skips atomically is skipped atomically here too:

    1. `text[i] == '"'` -> `_lex_quoted_segment`. `None` (an unterminated
       double-quoted identifier) -> decline the whole text.
    2. Otherwise `_skip_quote_or_comment` (single-quoted literal, `--` line comment,
       `/* */` block comment, dollar-quoted string). `None` (any of those left
       unterminated) -> decline the whole text. A returned index `!= i` means the
       region was skipped atomically, so nothing inside it is ever inspected and a
       `;` inside it can never become a boundary.
    3. `(` increments a depth counter; `)` decrements it with `max(0, depth - 1)` --
       the same floor the two helpers above already use, so an excess `)` can never
       drive depth negative.
    4. `;` **at depth == 0** closes the current statement at `text[start:i]` (the `;`
       itself belongs to neither neighbour) and starts the next at `i + 1`.
    5. Any other character, at any depth: advance one position.

    After the loop the final `text[start:]` is closed out as the last statement.

    Then each cut segment is classified, and this is the fail-closed half:

      * `_is_sql_ish` fires -> kept, and becomes one counted subject.
      * neither `_is_sql_ish` nor `_implies_table_position` fires -> dropped. Such a
        segment can hide nothing the whole-text scan would have found: every keyword
        `_extract_table_identifiers`/`_dangling_keywords` can match on
        (`_TABLE_KEYWORD_RE`) is a subset of `_TABLE_POSITION_KEYWORDS`, so
        `_implies_table_position` returning False proves the segment carries no table
        position for either to resolve or to refuse. Trailing whitespace after a final
        `;` is the ordinary case here.
      * `_implies_table_position` fires but `_is_sql_ish` does not -> **decline the
        whole text**. That segment carries a table position with no trigger verb of
        its own, so scanning it alone would return early at `_is_sql_ish` and lose a
        refusal the whole-text scan does make -- `SELECT 1; FROM` must stay one
        subject and stay a dangling-keyword ERROR, never become one clean statement.

    Declining returns `[text]`, which is literally the pre-increment subject, so every
    decline path reproduces the coarser accounting this increment replaces rather than
    a finer claim this walk could not establish. A text with no depth-0 `;` at all
    likewise yields `[text]`.

    `_is_sql_ish`/`_implies_table_position` are regex searches over raw slices and `;`
    is not a word character, so a `\\b`-delimited keyword match inside a segment is a
    match inside `text` and vice versa: no cut can create or destroy one.

    This function performs no I/O and mutates no argument."""
    segments: list[str] = []
    depth = 0
    start = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            lexed = _lex_quoted_segment(text, i)
            if lexed is None:
                return [text]
            _, i = lexed
            continue
        skipped = _skip_quote_or_comment(text, i)
        if skipped is None:
            return [text]
        if skipped != i:
            i = skipped
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0 and ch == ";":
            segments.append(text[start:i])
            start = i + 1
            i += 1
            continue
        i += 1
    if not segments:
        # No lexically certain boundary anywhere: the one subject it already was.
        return [text]
    segments.append(text[start:])
    kept: list[str] = []
    for segment in segments:
        if _is_sql_ish(segment):
            kept.append(segment)
        elif _implies_table_position(segment):
            return [text]
    return kept


def _dynamic_import_bindings(tree: ast.AST) -> frozenset[str]:
    """Names this file actually bound to `importlib.import_module` via
    `from importlib import import_module` or `... as <alias>` (R1-F05).

    Taken from the import statement, not from the called name: a local
    `def import_module(...)` with no such import binds nothing here, so
    calling it stays admissible. Only absolute `from importlib import ...`
    counts -- `from .importlib import import_module` (level > 0) is an
    unrelated local module. The binding is file-wide rather than
    lexically scoped, which can only over-approximate (toward ERROR), the
    fail-closed direction.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    bound.add(alias.asname or alias.name)
    return frozenset(bound)


def _builtins_module_bindings(tree: ast.AST) -> frozenset[str]:
    """Names this file actually bound to the stdlib `builtins` module via
    `import builtins` or `import builtins as <alias>` (R1-F05).

    Same shape and rationale as `_dynamic_import_bindings`: the receiver name
    is taken from the import statement, so an unrelated local object that
    merely happens to be spelled `builtins` (or spelled like the alias) binds
    nothing here and calling its `__import__` stays admissible, while
    `<bound>.__import__(...)` -- which the literal `importlib` receiver check
    could not see -- is recognised. Only a plain `import builtins` counts;
    the binding is file-wide rather than lexically scoped, which can only
    over-approximate (toward ERROR), the fail-closed direction.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "builtins":
                    bound.add(alias.asname or alias.name)
    return frozenset(bound)


def _importlib_module_bindings(tree: ast.AST) -> frozenset[str]:
    """Names this file actually bound to the stdlib `importlib` module via
    `import importlib`, `import importlib as <alias>`, or `import
    importlib.<sub>` (which binds the top-level name `importlib`) -- R1-F05.

    Same shape and rationale as `_builtins_module_bindings`. `import
    importlib.util as <alias>` is deliberately excluded: that alias is bound to
    the submodule, which carries no `import_module`/`__import__` of its own.
    The literal name `importlib` is treated as a receiver whether or not this
    resolver finds a binding for it (see `_is_importlib_receiver`), so adding
    alias recognition can only widen the ERROR set -- the fail-closed
    direction -- never narrow what the literal check already caught.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    bound.add(alias.asname or alias.name)
                elif alias.name.startswith("importlib.") and alias.asname is None:
                    bound.add("importlib")
    return frozenset(bound)


# The two attributes of the `importlib` module that perform a dynamic import.
_IMPORTLIB_DYNAMIC_ATTRS = ("import_module", "__import__")


def _is_importlib_receiver(node: ast.AST, importlib_names: frozenset[str]) -> bool:
    """A name this file bound to the stdlib `importlib` module -- or the literal
    name `importlib`, kept unconditionally so the pre-existing literal-receiver
    coverage cannot regress if the binding statement is absent or unparsed."""
    return isinstance(node, ast.Name) and (node.id == "importlib"
                                           or node.id in importlib_names)


def _is_dynamic_import_getattr(node: ast.Call, builtins_names: frozenset[str],
                               importlib_names: frozenset[str]) -> bool:
    """R1-F05 (`getattr` idiom): `getattr(importlib, "import_module")(...)` reaches
    the same dynamic import through a *call* in the receiver position, which the
    `ast.Name`/`ast.Attribute` branches structurally cannot see.

    The `getattr` retrieval itself is the finding, not only an
    immediately-applied call, so the two-step
    `_load = getattr(importlib, "import_module")` / `_load(...)` form is caught
    at the retrieval rather than needing dataflow. A non-constant attribute
    argument (`getattr(importlib, name)`) is also a finding: on a dynamic-import
    receiver the attribute cannot be statically resolved, so the only
    fail-closed answer is ERROR. A shadowed local `getattr` can likewise only
    over-approximate toward ERROR.
    """
    f = node.func
    if not (isinstance(f, ast.Name) and f.id == "getattr" and len(node.args) >= 2):
        return False
    receiver, attr = node.args[0], node.args[1]
    if _is_importlib_receiver(receiver, importlib_names):
        wanted = _IMPORTLIB_DYNAMIC_ATTRS
    elif isinstance(receiver, ast.Name) and receiver.id in builtins_names:
        wanted = ("__import__",)
    else:
        return False
    if isinstance(attr, ast.Constant) and isinstance(attr.value, str):
        return attr.value in wanted
    return True  # statically unresolvable attribute of a dynamic-import receiver


def _is_dynamic_import_call(node: ast.AST, dynamic_names: frozenset[str] = frozenset(),
                            builtins_names: frozenset[str] = frozenset(),
                            importlib_names: frozenset[str] = frozenset()) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Name):
        if f.id == "__import__" or f.id in dynamic_names:
            return True
        return _is_dynamic_import_getattr(node, builtins_names, importlib_names)
    if isinstance(f, ast.Attribute):
        # R1-F05: the receiver may be an `import importlib as <alias>` binding, not
        # only the literal name `importlib`.
        if _is_importlib_receiver(f.value, importlib_names) and f.attr in _IMPORTLIB_DYNAMIC_ATTRS:
            return True
        if not isinstance(f.value, ast.Name):
            return False
        # R1-F05: `import builtins; builtins.__import__(...)` is the same dynamic
        # import reached through a receiver the literal `importlib` check misses.
        return f.attr == "__import__" and f.value.id in builtins_names
    return False


# R1-F05 (`exec` idiom). The builtin `exec` runs arbitrary source -- including
# `import` statements -- in the inspected file's own process. Round-1 review of
# this gate found `exec("from app.modules.billing.internals import s")` a silent
# exit-0 PASS: the import sits inside a string constant, which the
# `ast.Import`/`ast.ImportFrom` walk structurally cannot see and which
# `_scan_sql_text` only ever examines for SQL. The receiver resolution below
# mirrors the one already built for `__import__`.
_EXEC_ATTR = "exec"

# Nesting cap for `exec("exec('...')")`. Exceeding it is a finding, never an
# admission -- the recursion only terminates early by *proving* import-freedom.
_EXEC_SOURCE_MAX_DEPTH = 8

# The literal name `exec` is always a dynamic-execution callee, exactly as the
# literal `__import__` is always a dynamic-import callee, so this is the default
# rather than an empty set: a caller that forgets to pass `_exec_bindings`
# still gets the bare-name coverage instead of silently losing the whole check.
_DEFAULT_EXEC_NAMES = frozenset({_EXEC_ATTR})


def _exec_bindings(tree: ast.AST) -> frozenset[str]:
    """Names this file can reach the builtin `exec` through as a bare name: the
    literal `exec`, plus any `from builtins import exec [as <alias>]` binding
    (R1-F05, `exec` idiom).

    The literal name is unconditional, as the bare `__import__` check is --
    `exec` is a builtin, so a file shadowing it with its own callable is the
    pathological case, and flagging that shadow can only over-approximate toward
    ERROR, the fail-closed direction. Only absolute `from builtins import ...`
    counts; `from .builtins import exec` (level > 0) is an unrelated local
    module. The binding is file-wide rather than lexically scoped, which again
    can only over-approximate toward ERROR.
    """
    bound = {_EXEC_ATTR}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "builtins":
            for alias in node.names:
                if alias.name == _EXEC_ATTR:
                    bound.add(alias.asname or alias.name)
    return frozenset(bound)


def _is_exec_callee(node: ast.Call, builtins_names: frozenset[str],
                    exec_names: frozenset[str]) -> bool:
    """Whether this call's callee is the builtin `exec` -- spelled as a bare name
    (`exec_names`) or as `<builtins binding>.exec`, the same two receiver shapes
    `_is_dynamic_import_call` already recognises for `__import__`."""
    f = node.func
    if isinstance(f, ast.Name):
        return f.id in exec_names
    if isinstance(f, ast.Attribute):
        return (f.attr == _EXEC_ATTR and isinstance(f.value, ast.Name)
                and f.value.id in builtins_names)
    return False


def _is_exec_retrieval_getattr(node: ast.Call, builtins_names: frozenset[str]) -> bool:
    """`getattr(<builtins binding>, "exec")` hands the builtin out with no source
    argument at the retrieval site, so no import-freedom proof is possible there
    and the retrieval itself is the finding -- the same reasoning, and the same
    deferred two-step coverage, as `_is_dynamic_import_getattr`.

    A non-constant attribute argument on a `builtins` receiver is already a
    dynamic-import finding, reported before this check runs, so it is not
    re-counted here.
    """
    f = node.func
    if not (isinstance(f, ast.Name) and f.id == "getattr" and len(node.args) >= 2):
        return False
    receiver, attr = node.args[0], node.args[1]
    return (isinstance(receiver, ast.Name) and receiver.id in builtins_names
            and isinstance(attr, ast.Constant) and isinstance(attr.value, str)
            and attr.value == _EXEC_ATTR)


def _exec_source_is_import_free(source: str, bindings: tuple[frozenset[str], ...],
                                depth: int = 0) -> bool:
    """Whether `source` *provably* carries no import of any kind.

    Static only: `ast.parse` parses the string, and nothing here executes,
    imports, compiles or evaluates it.

    Fail-closed on every unresolvable answer -- unparseable source, nesting past
    `_EXEC_SOURCE_MAX_DEPTH`, a dynamic-import call, an `exec` retrieval, and a
    nested `exec` whose own source is not provably import-free all return False.
    The enclosing file's bindings are reused rather than re-resolved against
    `source`, because any `import` statement inside `source` -- which is what a
    fresh binding would require -- already rejects it on the first branch below.
    """
    if depth > _EXEC_SOURCE_MAX_DEPTH:
        return False
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return False
    dynamic_names, builtins_names, importlib_names, exec_names = bindings
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False
        if not isinstance(node, ast.Call):
            continue
        if _is_dynamic_import_call(node, dynamic_names, builtins_names, importlib_names):
            return False
        if _is_exec_retrieval_getattr(node, builtins_names):
            return False
        if (_is_exec_callee(node, builtins_names, exec_names)
                and not _exec_call_is_import_free(node, bindings, depth + 1)):
            return False
    return True


def _exec_call_is_import_free(node: ast.Call, bindings: tuple[frozenset[str], ...],
                              depth: int = 0) -> bool:
    """Whether an `exec` call's source argument is a string literal that is
    provably import-free.

    Anything else is not statically resolvable, so the fail-closed answer is
    False: no argument at all, a bare name or attribute, an f-string, a `+`/`%`
    concatenation, `bytes`, a starred unpacking, or a pre-compiled code object.
    """
    if not node.args:
        return False
    first = node.args[0]
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return False
    return _exec_source_is_import_free(first.value, bindings, depth)


# --- R1-F06 (GATE2-R1-F06-JOIN-ASSEMBLED-SQL-2026-10-05): `str.join` assembly ----
#
# Round-1 review R1-F06 recorded a silent exit-0 PASS for
# `" ".join(["SELECT a", "FROM bil_invoices"])`: the per-`ast.Constant` scan sees
# only one fragment at a time, and no fragment carries a resolvable table
# position on its own ("SELECT a" triggers but has no table position; "FROM x"
# does not even trigger), so `_scan_sql_text` returns clean for each in turn and
# the assembled statement is never examined by anything.
#
# The branch below treats a `.join` whose literal fragments spell SQL-ish text as
# `MODULE_DEPS_SOURCE_UNINSPECTABLE`, which is ADR-011 D7.1's "runtime assembly"
# arm, and is the same polarity this function's existing `JoinedStr` and `BinOp`
# branches already apply -- `"SELECT * FROM membership_roster" + " WHERE id = 1"`
# is UNINSPECTABLE today even though it is fully literal and its table is
# correctly owned. Treating `.join` identically is therefore consistency with the
# established in-function rule, not a new policy; `.join` was simply an
# unenumerated shape in the same closed set.
_JOIN_ATTR = "join"
# A non-literal separator cannot be reproduced exactly, so both extremes are
# tried: a single space (fragments stay separate words) and the empty string
# (adjacent fragments fuse into one word). `_is_sql_ish` matches on word
# boundaries, so a verb may be visible under one and not the other -- testing
# both is strictly more fail-closed than picking one and guessing.
_JOIN_UNKNOWN_SEPARATORS = (" ", "")


# --- R1-F06 (GATE2-R1-F06-INTERPOLATED-VERB-FSTRING-2026-10-05): the verb in the hole
#
# Round-1 review R1-F06 also recorded a silent exit-0 PASS for
# `f"{op} a FROM bil_invoices"`. The `JoinedStr` branch below requires
# `_is_sql_ish` of the *literal* parts, and the literal parts here are
# `" a FROM bil_invoices"` -- `FROM` is a `_TABLE_POSITION_KEYWORDS` entry, not a
# `_TRIGGER_VERBS` entry, so `_is_sql_ish` is False and the branch never fires.
# The per-`ast.Constant` path cannot save it either: `_scan_sql_text` returns on
# that same `_is_sql_ish` check before extracting anything. So the statement has a
# fully literal, resolvable table position and the only thing missing from the
# static text is the DML verb -- which the interpolation supplies at runtime.
# Verified against the pre-fix code by direct execution, not inferred.
#
# The fail-closed question is therefore not "is this text SQL?" but "could some
# hole content make this text SQL with a table position the scanner would have
# examined?" -- and if the literal parts already carry a table position, the
# answer is yes for any hole content spelling a verb. That is the condition the
# branch keys on, via `_implies_table_position` (the same disjunction ADR-011
# D6.3's I-1 backstop already uses, now shared so the two cannot drift).
#
# Polarity is the same `MODULE_DEPS_SOURCE_UNINSPECTABLE` / D7.1 runtime-assembly
# arm every other branch in this function applies; it is not a new policy.
#
# DISCLOSED OVER-APPROXIMATION (deliberate, in the ERROR direction only): the
# table-position test is this module's regex keyword classifier, not a parser, so
# an f-string of ordinary prose that happens to contain FROM/JOIN/INTO/UPDATE/
# TABLE/ONLY/REFERENCES as a word -- `f"loaded {n} rows from cache"` -- is
# reported too. This is the same cost D6.1 already accepted explicitly ("a trigger
# over-approximation, not a detector allow-list -- widening it can only ever yield
# strictly more ERRORs, never a silent PASS"). Narrowing by requiring the keyword
# to be uppercase as written was considered and REJECTED: it would reintroduce the
# identical fail-open for lowercase SQL (`f"{op} a from bil_invoices"`). Measured
# against the live gate scope (`backend/app/modules/**`) at authoring time: 0 of 0
# f-strings newly reported, so this adds no current ERROR to the repository.


# --- R1-F06 (GATE2-R1-F06-FRAGMENT-LIST-CONCAT-2026-10-05): fragments in a bare list
#
# The third and last idiom round-1 review R1-F06 recorded as a silent exit-0 PASS,
# distinct from the two already closed above. The review's reproducer row reads
# "list element then concat at runtime" and its source is
# `PARTS = ['SELECT a', 'FROM bil_invoices']` -- the fragments sit in a bare
# sequence display and whatever concatenates them (a `for` loop, `+=`, a `.join`
# on the *name* in another function, a caller in another file) is nowhere near
# this node. Confirmed PASS on the pre-fix code by direct execution of the
# review's own harness, alongside the `.join` and interpolated-verb shapes which
# now ERROR -- so this is a live residual of F06, not a re-report of either fix.
#
# Why neither closed branch reaches it: `_join_assembly_candidates` requires the
# display to *be* a `.join` argument, and the per-`ast.Constant` scan sees one
# fragment at a time -- `"SELECT a"` triggers `_is_sql_ish` but carries no table
# position, so `_scan_sql_text` clears it at the D6.3 I-1 backstop, and
# `"FROM bil_invoices"` does not trigger at all. The fully literal, fully visible
# table name is never examined by anything.
#
# PREDICATE, and why it is deliberately NARROWER than the `.join` branch's: this
# branch fires only when an assembled candidate is BOTH `_is_sql_ish` AND
# `_implies_table_position` -- which is exactly the pair of conditions under which
# that same text, had it been written as one literal, would have reached
# `_scan_sql_text`'s table examination (its dangling-keyword check, identifier
# extraction, or the D6.3 I-1 backstop) instead of being cleared. The `.join`
# branch keys on `_is_sql_ish` alone, which it can afford: `.join` is the author
# writing "assemble a string here". A bare sequence display carries no such
# signal and is one of the most common shapes in ordinary Python, so requiring a
# table position keeps `("id", "select")`-style tuples admissible while leaving
# the reviewed form -- verb fragment plus table-position fragment -- reported.
# The result is never weaker than the single-literal path and sometimes stronger
# (a fully literal, correctly-owned statement split across elements is
# UNINSPECTABLE, the same parity the `.join` and `BinOp` branches already apply).
#
# Polarity is the same `MODULE_DEPS_SOURCE_UNINSPECTABLE` / ADR-011 D7.1
# runtime-assembly arm as every other branch in this function; not a new policy.
#
# DISCLOSED over-approximation (ERROR direction only), inherited from the keyword
# classifiers rather than added here: a sequence of ordinary prose that spells a
# trigger verb and a table-position keyword across its elements --
# `["select the row", "from cache"]` -- is reported. Same cost ADR-011 D6.1
# accepts explicitly for the trigger set. Narrowing by requiring the fragments to
# look like SQL *clauses*, or by requiring the concatenation site to be visible,
# was considered and REJECTED: both reintroduce a shape-bound closed set, which is
# the root cause (RC-1) F06 exists to remove. Measured against the live gate scope
# (`backend/app/modules/**`) at authoring time, by walking all 22 .py files there:
# 0 literal-bearing sequence displays exist at all, hence 0 newly reported, so
# this adds no current ERROR to the repository.
#
# RESIDUAL, stated rather than implied: a fragment sequence with no literal text
# at all (`[a, b]`), and fragments distributed across separate statements or
# across files (`A = "SELECT a"` / `B = "FROM bil_invoices"` concatenated later),
# are still PASS. Cross-statement dataflow is not in this increment.


def _literal_sequence_parts(node: ast.AST) -> tuple[str, ...] | None:
    """The per-element literal text of a literal sequence display, element order
    preserved, with a non-literal element (a name, a call, a starred unpacking)
    contributing an empty hole rather than a guess -- so any text built from the
    result is a *lower* bound on what the sequence really holds.

    Returns `None` for anything that is not a `List`/`Tuple`/`Set` display, and
    for a display whose elements carry no literal text at all (nothing to assert
    about an entirely dynamic sequence). Shared by `_join_assembly_candidates`
    and `_fragment_sequence_candidates` so the two R1-F06 assembly shapes read
    the same literal fragments the same way and cannot drift apart.
    """
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    parts = tuple(elt.value if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                  else "" for elt in node.elts)
    if not any(parts):
        return None
    return parts


def _join_assembly_candidates(node: ast.AST) -> tuple[str, ...]:
    """The statically-visible text a `<sep>.join(<elements>)` call could assemble.

    Static only: nothing here evaluates, imports or formats anything -- the
    candidates are built from string literals already present in the AST.

    A non-literal element contributes an empty hole rather than a guess (see
    `_literal_sequence_parts`), so each candidate is a *lower* bound on the real
    assembled text: exactly what the literal fragments alone already spell.
    Returns `()` -- the no-finding answer -- for anything that is not a `.join`
    call over a literal element sequence, and for a sequence whose elements carry
    no literal text at all (nothing to assert about an entirely dynamic join).
    """
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == _JOIN_ATTR and len(node.args) == 1):
        return ()
    parts = _literal_sequence_parts(node.args[0])
    if parts is None:
        return ()
    separator = node.func.value
    if isinstance(separator, ast.Constant) and isinstance(separator.value, str):
        return (separator.value.join(parts),)
    return tuple(sep.join(parts) for sep in _JOIN_UNKNOWN_SEPARATORS)


def _fragment_sequence_candidates(node: ast.AST) -> tuple[str, ...]:
    """The statically-visible text a bare literal sequence display could assemble
    once something concatenates its elements at runtime.

    Same lower-bound discipline as `_join_assembly_candidates`, with no separator
    known at this site at all -- the concatenation happens elsewhere -- so both
    `_JOIN_UNKNOWN_SEPARATORS` extremes are tried, exactly as the `.join` branch
    does for a non-literal separator.
    """
    parts = _literal_sequence_parts(node)
    if parts is None:
        return ()
    return tuple(sep.join(parts) for sep in _JOIN_UNKNOWN_SEPARATORS)


def _join_argument_sequences(tree: ast.Module) -> frozenset[int]:
    """The `id()`s of the sequence displays that are already a `<sep>.join(...)`
    argument in this file, so the fragment-sequence branch stays silent on them
    and the `.join` branch keeps its own, more specific report.

    Identity, not value: the walk below visits the `Call` and its argument
    display as two separate nodes of one live tree, and two textually identical
    displays elsewhere in the file must not suppress each other. Suppression
    loses no detection, because wherever the separator is a literal the `.join`
    branch knows the assembled text *exactly*, which is strictly better
    information than this branch's two-extreme lower bound.
    """
    return frozenset(
        id(node.args[0]) for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == _JOIN_ATTR and len(node.args) == 1
        and isinstance(node.args[0], (ast.List, ast.Tuple, ast.Set))
    )


def _uninspectable_for_node(node: ast.AST, relpath: str,
                            dynamic_names: frozenset[str] = frozenset(),
                            builtins_names: frozenset[str] = frozenset(),
                            importlib_names: frozenset[str] = frozenset(),
                            exec_names: frozenset[str] = _DEFAULT_EXEC_NAMES,
                            join_argument_ids: frozenset[int] = frozenset()) -> list[Violation]:
    """The closed set of statically-unprovable constructs (TSD §24.1 gate 2);
    never extended with an "etc." case. `dynamic_names`, `builtins_names`,
    `importlib_names`, `exec_names` and `join_argument_ids` come from
    `_dynamic_import_bindings` / `_builtins_module_bindings` /
    `_importlib_module_bindings` / `_exec_bindings` / `_join_argument_sequences`
    for the file this node belongs to."""
    loc = f"{relpath}:{getattr(node, 'lineno', 0)}"
    if _is_dynamic_import_call(node, dynamic_names, builtins_names, importlib_names):
        return [Violation("MODULE_DEPS_SOURCE_UNINSPECTABLE", loc,
                          "dynamic import call (__import__/importlib.import_module/"
                          "importlib.__import__ on the literal name or on an "
                          "`import importlib [as ...]` binding, the same two "
                          "attributes reached through `getattr(<importlib>, ...)`, "
                          "a name this file bound to "
                          "importlib.import_module via `from importlib import "
                          "import_module [as ...]`, or `__import__` on the stdlib "
                          "builtins module this file bound via `import builtins "
                          "[as ...]`, directly or via getattr) cannot be "
                          "statically resolved")]
    if isinstance(node, ast.Call):
        # R1-F05 (`exec` idiom), checked after the dynamic-import branch above so
        # a `getattr(<builtins>, <non-constant>)` is reported once, as the
        # dynamic import it already is, rather than twice.
        if _is_exec_retrieval_getattr(node, builtins_names):
            return [Violation("MODULE_DEPS_SOURCE_UNINSPECTABLE", loc,
                              "`getattr(<builtins>, 'exec')` retrieves the builtin `exec` "
                              "with no source argument at the retrieval site, so the source "
                              "it will later run cannot be shown import-free")]
        if (_is_exec_callee(node, builtins_names, exec_names)
                and not _exec_call_is_import_free(
                    node, (dynamic_names, builtins_names, importlib_names, exec_names))):
            return [Violation("MODULE_DEPS_SOURCE_UNINSPECTABLE", loc,
                              "exec of source that is not provably import-free (an "
                              "admissible source is a string literal whose parsed AST "
                              "carries no import statement, no dynamic-import call and no "
                              "further exec); exec runs `import` statements the static "
                              "walk cannot see")]
        # R1-F06 (`str.join` assembly), checked last in this block so a node that
        # is also a dynamic-import or `exec` finding keeps that stronger, more
        # specific report rather than being relabelled as join assembly.
        if any(_is_sql_ish(text) for text in _join_assembly_candidates(node)):
            return [Violation("MODULE_DEPS_SOURCE_UNINSPECTABLE", loc,
                              "`str.join` assembly whose literal fragments spell SQL-ish "
                              "text; the statement exists only once the join runs, so no "
                              "single fragment carries a scannable table position on its "
                              "own (ADR-011 D7.1 runtime assembly)")]
    # R1-F06 (fragment sequence, concatenated at runtime elsewhere), suppressed on
    # a display this file already passes to `.join` so the branch above keeps its
    # own, more specific report for that shape rather than both firing on one
    # construct.
    if (isinstance(node, (ast.List, ast.Tuple, ast.Set))
            and id(node) not in join_argument_ids
            and any(_is_sql_ish(text) and _implies_table_position(text)
                    for text in _fragment_sequence_candidates(node))):
        return [Violation("MODULE_DEPS_SOURCE_UNINSPECTABLE", loc,
                          "sequence of string literals whose fragments together spell "
                          "SQL-ish text carrying a table position; the statement exists "
                          "only once something concatenates the elements, so no single "
                          "fragment is ever scanned against a table position (ADR-011 "
                          "D7.1 runtime assembly)")]
    if isinstance(node, ast.JoinedStr):
        literal = "".join(v.value for v in node.values
                          if isinstance(v, ast.Constant) and isinstance(v.value, str))
        if any(isinstance(v, ast.FormattedValue) for v in node.values):
            if _is_sql_ish(literal):
                return [Violation("MODULE_DEPS_SOURCE_UNINSPECTABLE", loc,
                                  "f-string with SQL-ish literal parts and an interpolated "
                                  "value")]
            # R1-F06 (interpolated verb), checked only once the literal parts have
            # been found NOT SQL-ish, so an f-string that is already reported above
            # keeps that more specific message rather than being relabelled. Because
            # of that ordering, `_implies_table_position`'s bare-table-verb-form
            # disjunct can never be the *sole* reason this branch fires -- every
            # token it matches (TRUNCATE/COPY/GRANT/REVOKE) is itself a
            # `_TRIGGER_VERBS` entry, so `_is_sql_ish` above would have returned
            # first. Only the table-position-keyword disjunct is load-bearing here;
            # the shared helper is used anyway so the two call sites cannot drift.
            if _implies_table_position(literal):
                return [Violation("MODULE_DEPS_SOURCE_UNINSPECTABLE", loc,
                                  "f-string whose literal parts carry a table position but no "
                                  "DML verb, with an interpolated value that could supply the "
                                  "verb; the statement exists only once the f-string is "
                                  "formatted, so the literal text alone never triggers the "
                                  "SQL scan (ADR-011 D7.1 runtime assembly)")]
    elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        for operand in (node.left, node.right):
            if (isinstance(operand, ast.Constant) and isinstance(operand.value, str)
                    and _is_sql_ish(operand.value)):
                return [Violation("MODULE_DEPS_SOURCE_UNINSPECTABLE", loc,
                                  "string concatenation (+ or %) with a SQL-ish string "
                                  "literal operand")]
    return []


def _import_violation(importer: str, target: str, resolved: str, relpath: str, lineno: int,
                      modules: Mapping[str, ModuleEntry]) -> Violation | None:
    subject = f"{importer} -> {target}"
    loc = f"{relpath}:{lineno}"
    if importer == SHARED_PACKAGE:  # architecture.md control 3: _shared stays domain-free
        return Violation(
            "CROSS_DOMAIN_SQL_IMPORT", subject,
            f"{SHARED_PACKAGE!r} (domain-free) imports domain module {target!r} "
            f"(domain {modules[target].domain}) via {resolved!r} at {loc}; {SHARED_PACKAGE!r} "
            "may not depend on any domain",
        )
    target_entry = modules[target]
    approved_iface = any(resolved == iface or resolved.startswith(iface + ".")
                         for iface in target_entry.public_interfaces)
    if importer == ROOT_IMPORTER:  # ADR-011 D4: _root is domain-free
        if approved_iface:
            return None
        return Violation(
            "CROSS_DOMAIN_SQL_IMPORT", subject,
            f"{ROOT_IMPORTER!r} (domain-free modules-root importer) imports {target!r} "
            f"(domain {target_entry.domain}) internal path {resolved!r} at {loc}; not one "
            f"of {target!r}'s declared public_interfaces; the TSD §6.3 bidirectional-pair "
            f"check is inapplicable -- {ROOT_IMPORTER!r} has no domain to pair",
        )
    importer_entry = modules[importer]
    if not approved_iface:
        return Violation(
            "CROSS_DOMAIN_SQL_IMPORT", subject,
            f"{importer!r} (domain {importer_entry.domain}) imports {target!r} "
            f"(domain {target_entry.domain}) internal path {resolved!r} at {loc}; not one of "
            f"{target!r}'s declared public_interfaces",
        )
    edge = BIDIRECTIONAL_PAIRS.get(frozenset({importer_entry.domain, target_entry.domain}))
    if edge is not None and edge != (importer_entry.domain, target_entry.domain):
        return Violation(
            "REVERSE_EDGE_NOT_EVENT_DRIVEN", subject,
            f"{importer!r} (domain {importer_entry.domain}) -> {target!r} "
            f"(domain {target_entry.domain}) via {resolved!r} at {loc}; TSD §6.3 permits only "
            f"{edge[0]} -> {edge[1]} synchronously, the reverse edge must remain event-driven",
        )
    return None  # approved application interface, or the one pinned §6.3 synchronous edge


def _is_substantive(tree: ast.Module) -> bool:
    body = tree.body
    if len(body) == 1 and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return False
    return bool(body)


# --- R1-F10 (GATE2-R1-F10-D64-DOCSTRING-EXCLUSION-2026-10-05): ADR-011 D6.4 -------
#
# Round-1 review F10's shape: the per-`ast.Constant` SQL scan cannot tell an
# executable string literal from a docstring, so ordinary English prose in a
# module/class/function docstring is classified SQL-ish by the D6.1 broad trigger-verb
# set and then mined for a table identifier. A sentence as mundane as
# "never select data from billing_invoice directly" carries a trigger verb (`select`),
# a table-position keyword (`from`) and an identifier another module owns, so the gate
# returns a permanent FAIL CROSS_DOMAIN_SQL_IMPORT against a comment -- a false
# positive no author can fix except by rewording prose, and one that erodes the
# gate's own signal.
#
# ADR-011 D6.4's remedy is deliberately the narrowest one available: exclude ONLY
# docstring *positions*, counted and disclosed, with the residual stated plainly.
# Everything else about the scan -- including every non-leading string literal, every
# string in an expression position, and the whole of the fail-closed dynamic-construct
# rule -- is untouched.


def _docstring_constant_ids(tree: ast.Module) -> frozenset[int]:
    """The `id()`s of the `str` `Constant` nodes sitting in a *docstring position* in
    this file, per ADR-011 D6.4's exact definition: `body[0]` of a `Module`,
    `ClassDef`, `FunctionDef` or `AsyncFunctionDef` is an `ast.Expr` whose `.value` is
    a `str` `Constant`. That is the same structural rule CPython's own
    `ast.get_docstring` applies, so this set cannot drift from what Python actually
    binds to `__doc__`.

    Identity, not value -- the same discipline `_join_argument_sequences` above
    applies, and for the same reason: `ast.walk` yields nodes with no parent link, so
    a node's position can only be recovered by pre-resolving it from the tree. Keying
    on the string's *text* instead would suppress every byte-identical executable
    literal elsewhere in the same file, which is precisely the fail-open this
    exclusion must not create.

    Nothing beyond the four docstring positions is excluded. A *non-leading* string
    statement -- `body[1]` of the same function, which Python does not bind to
    `__doc__` -- is absent from this set and stays scanned, as does an
    attribute/variable "docstring" (PEP 258's convention, likewise not bound to
    `__doc__`), a string in any expression position, and every `.sql` file. An
    f-string in docstring position is a `JoinedStr`, not a `Constant`, so it is not
    collected here and keeps reaching the fail-closed dynamic-construct rule.
    """
    ids: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        if not node.body or not isinstance(node.body[0], ast.Expr):
            continue
        value = node.body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            ids.append(id(value))
    return frozenset(ids)


def _d64_docstring_note(count: int, *, partial: bool = False) -> str:
    """ADR-011 D6.4's mandatory disclosure: the excluded-position count plus the
    explicit residual the exclusion creates.

    Emitted on every module-deps return, including when `count` is 0 and including
    the ERROR paths: a reader must be able to tell "this run excluded nothing" from
    "this run excluded something and did not say so", and the residual is a property
    of the rule, not of a particular run's verdict. On an aborted run the count is
    labelled NOT FINAL rather than reading as a complete figure.

    `partial`'s label deliberately avoids the PARTIAL/LOWER BOUND wording ADR-011
    D5.5 uses for the *coverage* disclosure. That vocabulary means "the coverage
    enumeration ran and established something before aborting", which is a different
    claim from this one; `test_d5_absent_modules_dir_discloses_not_started_rather_than_nothing`
    asserts the coverage vocabulary appears in no note on a run where that pass never
    started, and borrowing it here would both break that check and blur the two
    disclosures a reader has to tell apart.

    `GateReport.notes` is part of `asdict()`, so this one string serves both the text
    and the `--json` surface.
    """
    scope = ("NOT FINAL -- this run aborted before the scan completed, so positions in "
             "files it never reached are not counted here"
             if partial else "complete for this run")
    return (
        f"ADR-011 D6.4 docstring exclusion: {count} docstring position(s) "
        "(module/class/function body[0] Expr Constant) withheld from the SQL scan, so "
        "English prose in a docstring is no longer a false FAIL CROSS_DOMAIN_SQL_IMPORT; "
        f"the count is {scope}. Every other string literal in the same file is still "
        "scanned, including a non-leading string statement whose text is byte-identical "
        "to the excluded docstring. RESIDUAL: a docstring is still a live runtime string "
        "reachable as `__doc__`, so SQL that reaches the database through `__doc__` is "
        "now examined by nothing -- it is NOT covered by the dynamic-construct rule "
        "(ADR-011 D7.1 MODULE_DEPS_SOURCE_UNINSPECTABLE), which keys on runtime-assembly "
        "shapes and never on a plain Constant, so this exclusion is an uncovered gap, not "
        "a fail-closed ERROR (GATE2-R1-F10-D64-DOCSTRING-EXCLUSION-2026-10-05)"
    )


# --- R1-F11 (GATE2-R1-F11-D62-BYTES-SQL-2026-10-05): ADR-011 D6.2 bytes literals ---
#
# Round-1 review F11's shape: the per-`ast.Constant` SQL scan tested
# `isinstance(node.value, str)`, so a `bytes` literal was not merely unattributed --
# it was never looked at. `Q = b'SELECT a FROM bil_invoices'` is an ordinary
# cross-domain query (psycopg accepts a `bytes` query string, so this is executable,
# not hypothetical) and the gate returned a clean verdict over it. That is a
# false-clean, which is the one direction this gate may never fail in.
#
# ADR-011 D6.2's remedy is narrow: decode the literal and feed the *existing*
# scanner. Nothing about statement triggering, identifier extraction or attribution
# changes, so a `bytes` literal and the `str` literal with the same text now reach
# exactly the same verdict by the same code path.

# ADR-011 D6.2's codec order, pinned as a named constant rather than inlined: the
# order is a contract (see `_decode_bytes_literal`), and naming it is also the seam
# the error-path test substitutes a genuinely-rejecting codec through, instead of
# pretending latin-1 can reject input.
_BYTES_LITERAL_CODECS: tuple[str, ...] = ("utf-8", "latin-1")


def _decode_bytes_literal(raw: bytes) -> str | None:
    """ADR-011 D6.2: decode a `bytes` literal for the SQL scan, trying
    `_BYTES_LITERAL_CODECS` in order, or return `None` if every codec rejects it.
    The caller converts `None` into `MODULE_DEPS_SOURCE_UNINSPECTABLE` (ERROR, exit 2
    -- D7.1's "reduction to statements/tokens failed or was impossible"), never into
    a skipped literal, which is R1-F11's own false-clean shape.

    The order is a contract, not a formality. `b"... FROM caf\\xc3\\xa9"` is UTF-8 for
    `café`; decoding latin-1 first would read it as `cafÃ©` and attribute characters
    the database will never see. latin-1 must therefore be second, and is the
    fallback precisely because it never rejects input -- trying it first would make
    UTF-8 unreachable.

    That same totality is why the `None` branch is defensive rather than reachable
    with the pinned pair: latin-1 maps all 256 byte values (asserted directly, over
    every value, by `test_f11_latin1_fallback_is_total_over_every_byte_value`), and
    an `ast.Constant` bytes value is always `bytes`, so no committed fixture can
    reach it. It exists so that narrowing this tuple later fails closed at exit 2
    instead of silently dropping literals from the scan, and
    `test_f11_undecodable_bytes_literal_is_uninspectable_error_not_a_silent_skip`
    exercises it by substituting a codec that genuinely rejects the input.

    `UnicodeDecodeError` only: an unknown codec name raises `LookupError`, which is a
    programming error in this tuple rather than a property of the input, and must
    surface through D7.3's outermost funnel rather than be swallowed as "undecodable
    input".
    """
    for codec in _BYTES_LITERAL_CODECS:
        try:
            return raw.decode(codec)
        except UnicodeDecodeError:
            continue
    return None


def _d62_bytes_note(scanned: int, undecodable: int, *, partial: bool = False) -> str:
    """ADR-011 D6.2's disclosure: how many `bytes` literals this run decoded and
    scanned, how many it could not decode, the codec order, and the residual the
    latin-1 fallback creates.

    Unconditional on every module-deps return for the same reason `_d64_docstring_note`
    is: `0 bytes literal(s)` is a different claim from a run that scanned some and said
    nothing, and the residual is a property of the rule rather than of one verdict. On
    an aborted run the counts are labelled NOT FINAL -- and, as in the D6.4 note,
    deliberately not with ADR-011 D5.5's PARTIAL/LOWER BOUND vocabulary, which carries
    the coverage pass's own different claim.
    """
    scope = ("NOT FINAL -- this run aborted before the scan completed, so literals in "
             "files it never reached are not counted here"
             if partial else "complete for this run")
    return (
        f"ADR-011 D6.2 bytes-literal SQL scan: {scanned} bytes literal(s) decoded and "
        f"scanned, {undecodable} undecodable and reported as "
        "MODULE_DEPS_SOURCE_UNINSPECTABLE at exit 2 rather than skipped; the counts are "
        f"{scope}. Decode order is UTF-8 then latin-1. A decoded bytes literal runs "
        "through the same statement trigger, identifier extraction and attribution as "
        "the byte-identical str literal, so the two reach the same verdict; until this "
        "increment a bytes literal was not a str Constant and so was never examined at "
        "all, which let b'SELECT a FROM bil_invoices' through as clean (R1-F11). D6.4's "
        "docstring exclusion is deliberately NOT extended to bytes: Python binds only a "
        "str body[0] to __doc__, so a bytes literal in body[0] position is executable "
        "text and stays scanned. RESIDUAL: latin-1 never rejects input, so a non-UTF-8 "
        "byte sequence is read as latin-1 text even when the database will read it "
        "under some other encoding -- a non-ASCII identifier in such a literal can be "
        "attributed from different characters than the ones actually sent, and a "
        "non-text binary payload is decoded and scanned like any other literal. Both "
        "over-approximate in the ERROR/violation direction only, never toward a clean "
        "verdict (GATE2-R1-F11-D62-BYTES-SQL-2026-10-05)"
    )


# --- R1-F12 (GATE2-R1-F12-D8-SQL-TRIGGER-COUNTER-2026-10-05): ADR-011 D8 -----------
#
# Round-1 review F12, on this one dimension: a module-deps clean verdict already
# discloses how many files were inspected (`N inspected file(s)`), how many docstring
# positions were withheld (D6.4) and how many bytes literals were decoded (D6.2) --
# but nothing at all about whether the SQL scanner ever recognised a SQL statement.
# A tree of pure `X = 1` assignments and a tree of real own-table queries therefore
# produce the same clean report, so the verdict carries no self-evidence that the
# ownership-relevant path -- statement triggering, identifier extraction, D3
# attribution -- ran over anything. ADR-011 D8 requires a clean verdict to
# self-evidence the inspection it claims; `N inspected file(s)` evidences only that
# files were opened.
#
# The counter is deliberately tied to *trigger recognition*, which is the exact
# condition under which `_scan_sql_text` goes on to examine table positions, and not
# to string volume. A Python string with no trigger verb, an f-string (a `JoinedStr`,
# never handed to the scanner), a number and a D6.4-excluded docstring each
# contribute nothing, so the count cannot be inflated into fake evidence by a file
# full of prose -- which is what would make it worthless as evidence.
#
# Scope: this increment counts recognised *statements* only. Per-identifier
# attribution-state counters (how many references resolved to which D3.2 state) and
# cross-module import-edge counters landed in their own later increments below; any
# relocation of the evidence set remains separate, still-unimplemented work.
_D8_SCOPE_COMPLETE = "complete"
_D8_SCOPE_PARTIAL = "partial"
_D8_SCOPE_NOT_STARTED = "not-started"


def _d8_trigger_note(count: int, scope: str = _D8_SCOPE_COMPLETE) -> str:
    """ADR-011 D8's self-evidence disclosure: how many text subjects this run's SQL
    scanner actually recognised as a SQL statement and therefore examined for table
    positions.

    Unconditional on every module-deps return, for the same reason
    `_d64_docstring_note` and `_d62_bytes_note` are: `0 text subject(s)` is a
    different claim from a run that recognised some and said nothing, and a reader
    must be able to tell a clean verdict that inspected real SQL from one that
    inspected none.

    Three scopes rather than `partial`'s two, because a zero has three distinct
    meanings here and D8 self-evidence cannot survive collapsing them.
    `_D8_SCOPE_COMPLETE` is a real total. `_D8_SCOPE_PARTIAL` is a run that aborted
    *during* the per-file scan, so the count is a minimum established by real
    inspection. `_D8_SCOPE_NOT_STARTED` is a run that aborted *before* the per-file
    scan began (an unusable --modules-dir or manifest, an undeclared discovered
    module): nothing was ever handed to the scanner, so the 0 records that no
    inspection happened and must not read as "no SQL-trigger text exists". The
    caller's discriminator is `coverage_disclosed`, which flips immediately before
    the scan loop.

    As in the D6.4/D6.2 notes, neither label borrows ADR-011 D5.5's
    PARTIAL/LOWER BOUND vocabulary or D5.5's own NOT_STARTED token: those carry the
    *coverage* pass's different claims, and blurring the two disclosures is the
    failure mode this wording avoids.

    `GateReport.notes` is part of `asdict()`, so this one string serves both the text
    and the `--json` surface.
    """
    if scope == _D8_SCOPE_COMPLETE:
        label = "the count is complete for this run"
    elif scope == _D8_SCOPE_PARTIAL:
        label = ("the count is NOT FINAL -- this run aborted during the per-file scan, so "
                 "subjects in files it never reached are not counted and this is a minimum "
                 "established by real inspection, not a total")
    elif scope == _D8_SCOPE_NOT_STARTED:
        label = ("the count is NOT STARTED -- this run aborted before the per-file scan "
                 "began, so nothing was ever handed to the scanner and a 0 here records "
                 "that no inspection happened, never that no SQL-trigger text exists")
    else:
        raise ValueError(f"unknown ADR-011 D8 trigger-note scope {scope!r}")
    return (
        f"ADR-011 D8 SQL-trigger inspection: {count} text subject(s) recognised as a SQL "
        "statement by the D6.1 trigger-verb set and therefore examined for table positions; "
        f"{label}. A subject is one SQL statement, cut from the text handed to the scanner "
        "-- a readable .sql file's text, a non-docstring str literal, or a decoded bytes "
        "literal -- at lexically certain top-level semicolon boundaries as of "
        "GATE2-R1-F12-D8-STATEMENT-SUBJECTS-2026-10-06, so a file holding three statements "
        "contributes 3 rather than 1; a semicolon inside a quoted literal, a comment, a "
        "dollar-quoted body, a double-quoted identifier or parentheses is never a boundary, "
        "and a text whose cut is not lexically certain is counted as the one coarse subject "
        "it was before that increment (see the zero-table note's LIMIT for that decline "
        "rule). A subject "
        "is counted only when the trigger actually fired, so a string with no trigger "
        "verb and a plain number each contribute nothing and the count cannot be inflated by "
        "prose volume. An f-string's own JoinedStr node is never a subject, but each of its "
        "literal fragments is an ordinary str Constant the walk yields separately, so a "
        "fragment carrying a trigger verb is counted as the subject it is while the "
        "interpolated whole it belongs to is refused by the fail-closed dynamic-construct "
        "rule (ADR-011 D7.1) and is never counted as inspected. "
        "This is what makes a clean verdict self-evidencing per ADR-011 D8: a tree of "
        "trivial assignments reports 0 here and so evidences nothing about table ownership, "
        "while a nonzero count shows the trigger/extraction/attribution path really ran over "
        "SQL text. RESIDUAL: this counts recognised statements, not table references -- a "
        "subject carrying a trigger verb but no table position (SELECT 1) counts the same as "
        "one carrying ten identifiers, so a nonzero count is evidence that the scanner "
        "looked, never a measure of how much it attributed; how much it attributed, and "
        "to which D3.2 state, is disclosed separately by the table-reference attribution "
        "note as of GATE2-R1-F12-D8-TABLE-STATE-COUNTERS-2026-10-05, and D8's remaining "
        "counted dimension -- cross-module import edges resolved and approved, which is "
        "about Python imports rather than SQL text and so contributes nothing here -- by "
        "the import-edge note as of "
        "GATE2-R1-F12-D8-IMPORT-EDGE-COUNTERS-2026-10-05. Text that was withheld or never "
        "decoded is necessarily absent here and must "
        "not be read as inspected: a D6.4-excluded docstring position is never handed to the "
        "scanner (see the docstring-exclusion note for that count) and an undecodable bytes "
        "literal is reported as MODULE_DEPS_SOURCE_UNINSPECTABLE instead of scanned (see the "
        "bytes-literal note for that count) "
        "(GATE2-R1-F12-D8-SQL-TRIGGER-COUNTER-2026-10-05)"
    )


# --- R1-F12 (GATE2-R1-F12-D8-TABLE-STATE-COUNTERS-2026-10-05): ADR-011 D8/D3.2 ----
#
# The second R1-F12/D8 dimension, on top of the statement-trigger counter above. That
# counter's own disclosed RESIDUAL was that it counts recognised *statements*, not
# table references: `SELECT 1` and a statement carrying ten identifiers both report
# "1 text subject". So a clean verdict still could not evidence that D3 attribution --
# the ownership decision the gate exists to make -- ran over a single identifier, nor
# which states those identifiers reached. ADR-011 D8 requires "table references by
# D3.2 state (own / other / CTE / system / declared external)" on every run.
#
# Scope held deliberately narrow, and the two exclusions are disclosed in the note
# rather than papered over:
#   * D3.2 state 3 (CTE-local) is **not** wired into the live scanner. The pure
#     `_collect_cte_names`/`_cte_scopes` helpers exist and stay unconnected per the
#     qualified U1/U2 B HOLD, so the CTE count is a structural zero. It is disclosed
#     as an unimplemented path -- never as "no CTE-bound reference occurred", and the
#     helper is not connected just to make the field look exercised.
#   * Cross-module *import*-edge counters (D8's "cross-module import edges resolved
#     and approved") are a separate dimension, landed in the increment below. The
#     counters here cover SQL table references only, and the two never overlap.


def _d8_table_ref_note(counts: _TableRefCounts, scope: str = _D8_SCOPE_COMPLETE) -> str:
    """ADR-011 D8's per-identifier disclosure: how many table-position identifiers this
    run actually extracted, and which D3.2 terminal state each reached.

    Unconditional on every module-deps return -- PASS, FAIL and ERROR -- for the same
    reason the three notes above are: an explicit `0` is a different claim from a run
    that attributed some and said nothing, and the residuals are properties of the
    rules rather than of one verdict.

    The three scopes are the trigger note's, reused rather than re-invented so the two
    D8 disclosures cannot drift apart in what a label means -- but the three claims this
    dimension can honestly make are NOT the three the other D8 notes make, and
    GATE2-R2-N01-D67-D8-LOWER-BOUND-TRUTHFULNESS-2026-10-06 separates them:

      * `_D8_SCOPE_COMPLETE` is a run whose per-file scan ran to completion. That is a
        statement about **file traversal**, and per ADR-011 D6.7.5 it is NOT permission
        to call these figures a total: the counters total *attributed extracted
        identifiers*, and nothing in this run establishes D6.7.2's per-position
        accounting over every subject. So a completed scan discloses a **lower bound**
        here, in the same terms ADR-011 D7.2 already uses for the FAIL-class partition.
      * `_D8_SCOPE_PARTIAL` is a run that aborted *during* the per-file scan, so the
        figures fall short for a second, independent reason -- files the run never
        reached -- and every field is a minimum established by real attribution.
      * `_D8_SCOPE_NOT_STARTED` is a run that aborted *before* the scan began, so
        nothing was ever attributed and the zeros record that no attribution happened --
        never that the tree contains no table reference.

    The three therefore stay semantically distinct: a shortfall in position accounting
    only, a shortfall in position accounting *and* file coverage, and no inspection at
    all. As in the notes above, none of the three borrows ADR-011 D5.5's
    PARTIAL/LOWER BOUND or NOT_STARTED coverage vocabulary, which carries the coverage
    pass's different claim.

    `GateReport.notes` is part of `asdict()`, so this one string serves both the text
    and the `--json` surface.
    """
    if scope == _D8_SCOPE_COMPLETE:
        # ADR-011 D6.7.5 (GATE2-R2-N01-D67-D8-LOWER-BOUND-TRUTHFULNESS-2026-10-06):
        # "the counts are complete for this run" used to be asserted here and was
        # affirmatively false. A completed per-file scan proves file traversal
        # finished; it does not prove D6.7.2's accounting held for every subject.
        # GATE2-R2-N01-D67-D8-RESIDUAL-ROOT-CAUSE-2026-10-06.md executed the
        # counterexample: a two-file run of `SELECT a FROM mem_roster` plus
        # `TRUNCATE mem_t, bil_invoices` finishes its scan and reports
        # own/other/unattributed 1/0/0 -- the bare-TRUNCATE positions yield no
        # position record at all -- while the old sentence called those counts
        # complete. The ERROR status refuses that tree, but it does not turn the
        # attribution figures into a total, and the sentence is the one a reader
        # relies on when judging what a verdict means. Until a run can carry an
        # explicit D6.7.2 position-totality proof, this branch discloses a lower
        # bound. The other two scopes are left exactly as they were: they already
        # claim less than this one, and each still names its own distinct shortfall.
        label = ("the per-file scan ran to completion, but these counts are a lower "
                 "bound and NOT a total -- every figure counts attributed extracted "
                 "identifiers only, and this run carries no explicit ADR-011 D6.7.2 "
                 "position-totality proof that every table position in every scanned "
                 "subject yielded an identifier that reached a D3.2 state, so a table "
                 "position the extractor did not recognise contributes nothing here "
                 "and its absence from these figures is never evidence that no such "
                 "position exists (a completed FILE scan is not a proved complete "
                 "TABLE-REFERENCE inventory)")
    elif scope == _D8_SCOPE_PARTIAL:
        label = ("the counts are NOT FINAL -- this run aborted during the per-file scan, "
                 "so references in files it never reached are not counted and every "
                 "figure here is a minimum established by real attribution, not a total")
    elif scope == _D8_SCOPE_NOT_STARTED:
        label = ("the counts are NOT STARTED -- this run aborted before the per-file scan "
                 "began, so no identifier was ever attributed and the zeros here record "
                 "that no attribution happened, never that the tree holds no table "
                 "reference")
    else:
        raise ValueError(f"unknown ADR-011 D8 table-reference-note scope {scope!r}")
    return (
        f"ADR-011 D8 table-reference attribution: {counts.total} table-position "
        f"identifier reference(s) extracted and attributed -- own (D3.2 state 1) "
        f"{counts.own}, another module's (state 2, FAIL CROSS_DOMAIN_SQL_IMPORT) "
        f"{counts.other}, CTE-local (state 3) {counts.cte}, reserved-system (state 4) "
        f"{counts.system}, declared-external (state 5) {counts.external}, unattributed "
        f"(state 6, ERROR MODULE_DEPS_TABLE_UNATTRIBUTED) {counts.unattributed}; "
        f"{label}. States 1 and 2 are reported separately even though both resolve to "
        "one owner-known outcome internally, because the own/other split is the "
        "ownership decision this gate exists to make. Each figure counts extracted "
        "identifier occurrences, not distinct table names and not statements: two "
        "references to one table are two, and a recognised statement with no table "
        "position at all (SELECT 1) contributes zero to every field while still "
        "counting as one inspected subject in the SQL-trigger note. "
        "The declared-external figure (state 5) counts identifiers OBSERVED in scanned "
        "SQL that resolved to a manifest declaration; it is NOT the inventory of what the "
        "manifest declares, which is listed by name with its own count in the declared "
        "external_table_references inventory note as of "
        "GATE2-R1-F12-D8-EXTERNAL-NAMES-2026-10-05 (ADR-011 D3.5) -- a declared entry no "
        "statement references is normal and leaves this figure 0, and one declaration "
        "referenced twice makes it 2, so the two numbers answer different questions and "
        "neither is a view of the other. "
        "LIMIT -- CTE-local (state 3) is structurally unreachable on this path and its "
        "count is therefore a genuine zero that records an unimplemented path, NOT an "
        "observation that no CTE-bound reference occurred: the live scanner calls the "
        "attribution helper with an empty CTE-name set, and lexical state-3 collection "
        "exists only as a pure, deliberately unconnected helper, so a WITH-bound name "
        "in table position is counted as unattributed (state 6, ERROR) rather than as a "
        "CTE. RESIDUAL: these are not totals of every table reference in the tree. Text "
        "the scanner never received contributes nothing and must not be read as "
        "attributed -- a D6.4-excluded docstring position, an undecodable bytes "
        "literal, an interpolated dynamic construct refused under D7.1, and anything "
        "outside --modules-dir. Neither does a subject the scanner recognised but could "
        "not reduce: a dangling table-position keyword and a D6.3 I-1 backstop hit each "
        "yield zero references here and are disclosed as "
        "MODULE_DEPS_SOURCE_UNINSPECTABLE instead. Cross-module import-edge counts "
        "(D8's other counted dimension) are disclosed separately by the import-edge note "
        "as of GATE2-R1-F12-D8-IMPORT-EDGE-COUNTERS-2026-10-05; they count Python import "
        "edges and never table references, so no figure here is a view of them. A "
        "nonzero own/other/system/external figure is positive evidence that D3 "
        "attribution really ran and reached that state; an all-zero complete count over "
        "a tree means no table-position identifier was extracted at all, so the verdict "
        "evidences nothing about table ownership "
        "(GATE2-R1-F12-D8-TABLE-STATE-COUNTERS-2026-10-05)"
    )


# --- R2-N01 (ADR-011 D6.8.6/D6.8.8): the privilege-list suppression disclosure -----
#
# D6.8 is the one clause in ADR-011 that *removes* refusal surface, so it is the one
# place where the report would otherwise go quiet about something the gate chose not to
# look at. D6.8.6 makes the trace mandatory rather than optional, in its own words:
# the suppression "must itself be countable at that site and **disclosed under D8 on
# every run including PASS**", because "a narrowing that leaves no trace in the report
# is indistinguishable, to a reader, from the silent under-extraction D6.7 exists to
# forbid".
#
# Two things this note must get right, and both are easy to get wrong:
#
#   1. The figure is a **run-wide aggregate**, summed across every subject the scanner
#      received (`_SuppressionCounts`, threaded from `run_module_deps_gate` through
#      `_scan_sql_text`/`_scan_sql_statement` into the merge point). A per-subject
#      figure would disclose the last subject's suppressions and silently drop the
#      rest, which is the original defect with a number painted on it.
#   2. It may not be read, by itself or in combination with the table-reference note,
#      as making that note's figure complete. D6.8.8 is explicit that D6.7.5 is
#      "unchanged and unweakened" -- the table-reference figure "remains a disclosed
#      **lower bound**", and "no reduction in the reported figure may be presented as
#      evidence of completeness". So this note states the relationship in the other
#      direction: suppression *lowers* the table-reference figure toward the truth
#      while leaving it a lower bound, and the reader is told so here rather than left
#      to infer it.
#
# Mutant M-E14 is the control: the counter hardcoded to zero, or this note's
# lower-bound wording replaced by a completeness claim. Neither moves a status, an exit
# code or a D3.2 figure, so like M-E6 only an exact-text assertion can kill it.


def _d68_suppression_note(counts: _SuppressionCounts,
                          scope: str = _D8_SCOPE_COMPLETE) -> str:
    """ADR-011 D6.8.6's suppression disclosure: how many table-position signals this
    run suppressed as privilege-list tokens, aggregated over every scanned subject.

    Unconditional on every module-deps return -- PASS, FAIL and ERROR -- for the same
    reason every D8 note above is, and for one more that is specific to this
    dimension: on PASS the suppression is the *only* evidence that the narrowing ran
    at all, since a suppressed signal leaves no violation and no table reference
    behind. `0 signal(s)` is a different claim from a run that suppressed some and
    said nothing.

    The three scopes are the other D8 notes', reused so a label cannot come to mean
    two things across the report, and each names this dimension's own shortfall:

      * `_D8_SCOPE_COMPLETE` -- the per-file scan ran to completion, so the figure is
        the run's whole suppression count. Unlike the table-reference note this figure
        really is a total *of suppressions*, because a suppression is an event at the
        one merge point rather than an inventory of something in the tree. What it is
        emphatically NOT is evidence that the table-reference figure is complete; that
        figure stays a D6.7.5 lower bound and this note says so.
      * `_D8_SCOPE_PARTIAL` -- aborted during the per-file scan, so subjects the run
        never reached could have suppressed more and the figure is a minimum.
      * `_D8_SCOPE_NOT_STARTED` -- aborted before the scan began, so nothing was ever
        examined and the zero records that no suppression decision was made, never
        that no suppressible signal exists in the tree.

    As in the notes above, none of the three borrows ADR-011 D5.5's reserved
    PARTIAL/LOWER BOUND/NOT_STARTED coverage vocabulary.

    `GateReport.notes` is part of `asdict()`, so this one string serves both the text
    and the `--json` surface."""
    if scope == _D8_SCOPE_COMPLETE:
        label = ("the per-file scan ran to completion, so this is the run's whole "
                 "suppression count -- and it is NOT evidence that the "
                 "table-reference figure is complete: per ADR-011 D6.7.5 that figure "
                 "remains a disclosed lower bound, and a figure this narrowing moved "
                 "nearer the truth is still a lower bound")
    elif scope == _D8_SCOPE_PARTIAL:
        label = ("the count is NOT FINAL -- this run aborted during the per-file scan, "
                 "so signals in subjects it never reached were never examined for "
                 "suppression and this figure is a minimum, while the table-reference "
                 "figure remains a disclosed ADR-011 D6.7.5 lower bound")
    elif scope == _D8_SCOPE_NOT_STARTED:
        label = ("the count is NOT STARTED -- this run aborted before the per-file scan "
                 "began, so no suppression decision was ever made and the zero here "
                 "records that, never that the tree holds no suppressible signal")
    else:
        raise ValueError(f"unknown ADR-011 D6.8 suppression-note scope {scope!r}")
    return (
        f"ADR-011 D6.8 privilege-list signal suppression: {counts.signals} "
        f"table-position signal(s) suppressed as privilege-list tokens, across "
        f"{counts.subjects} scanned subject(s); {label}. The figure is an aggregate "
        "over every subject this run handed the scanner -- a .sql file's text, a str "
        "literal, a decoded bytes literal -- never one subject's figure. It counts "
        "suppressed SIGNALS, not statements and not distinct keywords: one statement "
        "suppressing both a TRUNCATE and an UPDATE contributes 2, and the same "
        "statement in two files contributes 2, while the subject figure beside it "
        "counts subjects in which at least one suppression occurred, so neither number "
        "is a view of the other. A signal is suppressed only under the one bounded "
        f"predicate of ADR-011 D6.8.1-D6.8.3: its keyword is one of "
        f"{'/'.join(sorted(_SUPPRESSIBLE_PRIVILEGE_SIGNALS))} (the derived "
        "intersection of the closed PostgreSQL privilege vocabulary with the signal "
        "sources' own keyword tokens), it lies wholly inside a positively-computed "
        "GRANT/REVOKE privilege-list region, and it sits at parenthesis depth 0 there. "
        "Every other signal is retained, and where the region cannot be positively "
        "computed the signal is retained too (D6.8.4: suppression is permitted only ON "
        "a bound, never FOR WANT OF one). "
        "LIMIT -- a nonzero figure here means refusal surface was deliberately removed, "
        "which is why it is disclosed rather than inferred: the removed positions were "
        "privilege names in a privilege list, whose own identifier was either absent or "
        "the reserved word ON that no module owns, so under D6.8.5 none of them carried "
        "a real table. That is the clause's constructive argument, not a measurement "
        "this run performed. RESIDUAL: this figure says nothing about positions the "
        "extractor never recognised in the first place -- those are the table-reference "
        "note's disclosed D6.7.5 residual and are a different shortfall from this one. "
        "A suppression and an unrecognised position both leave no table reference "
        "behind, and only this figure tells them apart"
    )


# --- R1-F12 (GATE2-R1-F12-D8-ZERO-TABLE-COUNTER-2026-10-05): ADR-011 D6.3 + D8 ----
#
# The two SQL counters above leave one claim unmade, and it is the claim D6.3 turns on.
# The trigger counter's own disclosed RESIDUAL is that "a subject carrying a trigger
# verb but no table position (SELECT 1) counts the same as one carrying ten
# identifiers"; the table-state counters then report zero references for that subject,
# exactly as they do for a subject the scanner refused as uninspectable. So on the
# report's two existing SQL surfaces a clean `SELECT 1` and a fail-closed
# `MODULE_DEPS_SOURCE_UNINSPECTABLE` refusal are indistinguishable: one recognised
# subject, zero attributed references, either way.
#
# They are opposite claims. ADR-011 D6.3 is explicit that a triggered subject with no
# table position at all is **clean** -- an unqualified "triggered but zero references
# => ERROR" rule would flag the most common operational SQL in existence -- while a
# subject that implies a table position it could not resolve (a dangling keyword, or
# the I-1 backstop's broader ONLY/REFERENCES/bare-verb condition) is ERROR at exit 2.
# This increment gives the clean class its own counter and keeps the two ERROR classes
# in their own separate figures, so neither can inflate it.
#
# Nothing about any decision changes: `_scan_sql_text`'s three early returns keep their
# exact existing behaviour, codes, violation texts, statuses and exit codes. The only
# new thing in the report is a count.


def _d8_zero_table_note(counts: _ZeroTableCounts,
                        scope: str = _D8_SCOPE_COMPLETE) -> str:
    """ADR-011 D6.3 + D8's zero-table disclosure: of the subjects this run's SQL
    scanner recognised, how many were clean with no table position at all, how many it
    refused as unresolvable, and how many reduced to real identifiers.

    Unconditional on every module-deps return -- clean verdict, FAIL and ERROR -- for
    the same reason the notes above are: an explicit `0` is a different claim from a
    run that counted some and said nothing, and the limit and residual are properties
    of the rules rather than of one verdict.

    The three scopes are the notes above's, reused rather than re-invented so no D8
    disclosure can drift from another in what a label means. `_D8_SCOPE_COMPLETE` is a
    real total for the supplied tree. `_D8_SCOPE_PARTIAL` is a run that aborted
    *during* the per-file scan, so every figure is a minimum established by real
    inspection. `_D8_SCOPE_NOT_STARTED` is a run that aborted *before* the scan began,
    so nothing was recognised at all and the zeros record that no inspection happened.
    As in the notes above, none of the three borrows ADR-011 D5.5's coverage
    vocabulary, which carries the coverage pass's different claim.

    `GateReport.notes` is part of `asdict()`, so this one string serves both the text
    and the `--json` surface.
    """
    if scope == _D8_SCOPE_COMPLETE:
        label = "the counts are complete for this run"
    elif scope == _D8_SCOPE_PARTIAL:
        label = ("the counts are NOT FINAL -- this run aborted during the per-file scan, "
                 "so subjects in files it never reached are not counted and every figure "
                 "here is a minimum established by real inspection, not a total")
    elif scope == _D8_SCOPE_NOT_STARTED:
        label = ("the counts are NOT STARTED -- this run aborted before the per-file scan "
                 "began, so no subject was ever recognised and the zeros here record that "
                 "no inspection happened, never that the tree holds no zero-table "
                 "statement")
    else:
        raise ValueError(f"unknown ADR-011 D6.3/D8 zero-table-note scope {scope!r}")
    return (
        f"ADR-011 D6.3/D8 zero-table triggered statements: of {counts.recognised} "
        f"recognised subject(s), {counts.clean} carried no table position at all and are "
        f"clean (SELECT 1, SELECT now(), a bare ANALYZE or VACUUM), {counts.unresolved} "
        "yielded no usable table identifier and are ERROR -- "
        f"{counts.dangling} refused by the dangling-keyword rule and {counts.implied} by "
        "the D6.3 I-1 backstop, both reported as MODULE_DEPS_SOURCE_UNINSPECTABLE at exit "
        f"2 -- and the remaining {counts.with_tables} reduced to at least one "
        "table-position identifier and are counted per identifier by the table-reference "
        f"attribution note instead; {label}. A clean zero-table statement is a counted "
        "inspection success, not an absence of inspection: the scanner recognised it, "
        "examined it for table positions and found none, which is why ADR-011 D6.3 "
        "refuses the unqualified rule \"triggered but zero references means ERROR\". The "
        "two unresolved classes make the opposite claim and are deliberately never folded "
        "into the clean figure -- each means a real table reference this scanner could not "
        "resolve, including every dangling-keyword and I-1 backstop case, so each fails "
        "closed and must never be read as a clean zero-table success. RECONCILIATION: the "
        "four figures partition the recognised-subject count with no overlap and no "
        "remainder, because each is incremented on exactly one of the scanner's own return "
        "paths, so their sum is by construction the figure the SQL-trigger inspection note "
        "reports and the two notes cannot disagree. The table-bearing figure is the count "
        "of *subjects* behind the table-reference attribution note's identifier total, "
        "which counts occurrences -- so that total is at least this figure, and is 0 "
        "exactly when this figure is 0. LIMIT -- every figure here counts SQL STATEMENTS, "
        "cut at lexically certain top-level semicolon boundaries "
        "(GATE2-R1-F12-D8-STATEMENT-SUBJECTS-2026-10-06), so a .sql file of ten table-free "
        "statements contributes 10 to the clean figure rather than 1, and a file mixing a "
        "table-free statement with a table-bearing one contributes 1 to the clean figure "
        "and 1 to the table-bearing figure rather than landing wholly in the latter. A "
        "semicolon inside a single-quoted literal, a line or block comment, a "
        "dollar-quoted body, a double-quoted identifier, or inside parentheses is never a "
        "boundary, so no statement is cut at one. Where the cut is NOT lexically certain "
        "segmentation is DECLINED and the whole text is accounted as the one coarse subject "
        "it was before that increment -- an unterminated literal, comment, dollar-quoted "
        "body or double-quoted identifier anywhere in the text, or a cut segment carrying a "
        "table position with no D6.1 trigger verb of its own, which must stay joined to its "
        "neighbours so its refusal cannot be lost. Every decline errs in the fail-closed "
        "direction: no text holding a table reference anywhere can then be counted clean. "
        "That decline is the remaining granularity limit, disclosed here rather than "
        "silently claimed. RESIDUAL: text the "
        "scanner never received contributes to no figure here and must not be read as "
        "examined -- a D6.4-excluded docstring position, an undecodable bytes literal, an "
        "interpolated dynamic construct refused under D7.1, and anything outside "
        "--modules-dir. Neither does a string the trigger never fired on, which is the one "
        "shape that is genuinely uninspected rather than inspected-and-table-free "
        "(GATE2-R1-F12-D8-ZERO-TABLE-COUNTER-2026-10-05)"
    )


# --- R1-F12 (GATE2-R1-F12-D8-IMPORT-EDGE-COUNTERS-2026-10-05): ADR-011 D8 ---------
#
# The third and last counted dimension ADR-011 D8 names: "cross-module import edges
# resolved and approved". The two counters above cover SQL text only -- how much the
# statement trigger fired on, and how many table-position identifiers each D3.2 state
# received. Neither says anything about the *import* half of the gate, which is the
# other half of what §24.1 constrains and the half `_import_violation` decides. So a
# clean verdict over a tree whose modules import each other through declared
# interfaces and a clean verdict over a tree with no cross-module import at all were
# still indistinguishable on this dimension.
#
# Two figures, for the same reason D8 names two: `resolved` is how many cross-module
# edge *occurrences* the scan actually put to the decision, and `approved` is how many
# of those the existing decision logic let through. The gap between them is the denied
# set, which already carries its own unchanged FAIL violation -- so the pair is a
# reconciliation against the violation list, not a second opinion about it.
#
# Nothing about the decision itself changes here: `_import_violation` is untouched,
# every short-circuit above it keeps its existing behaviour, and an import target that
# names no declared module stays `MODULE_DEPS_GATE_INPUT_INVALID` at exit 2.


@dataclass
class _ImportEdgeCounts:
    """ADR-011 D8's "cross-module import edges resolved and approved" counters
    (GATE2-R1-F12-D8-IMPORT-EDGE-COUNTERS-2026-10-05), accumulated by
    `run_module_deps_gate`'s import branch and held outside its `try` for the same
    reason `_TableRefCounts` is: whatever the run really established must survive into
    the ERROR report built by the `except GateInputError` handler, labelled as a
    minimum rather than discarded with the frame or read as a total.

    `resolved` counts an edge *occurrence* -- one `Import`/`ImportFrom` alias target
    that resolved under the modules root to a declared module other than the importer
    and other than `_shared`. `approved` counts the subset `_import_violation` returned
    no violation for. Occurrences, not distinct `(importer, target)` pairs: two imports
    of the same interface are two, which keeps the pair reconcilable against the
    violation list rather than against a deduplicated edge set.

    The two are deliberately not collapsed into one "denied" figure. `resolved` alone
    says the decision ran; `approved` alone cannot distinguish "every edge was
    approved" from "there were no edges", which is exactly the self-evidence D8 asks
    for."""
    resolved: int = 0
    approved: int = 0

    @property
    def denied(self) -> int:
        """Derived, never accumulated separately: a denied edge is by definition a
        resolved one the decision refused, so deriving it makes the two figures
        impossible to drift apart."""
        return self.resolved - self.approved


def _d8_import_edge_note(counts: _ImportEdgeCounts,
                         scope: str = _D8_SCOPE_COMPLETE) -> str:
    """ADR-011 D8's import-edge disclosure: how many cross-module Python import edges
    this run resolved to a declared module and put to the dependency decision, and how
    many of those that decision approved.

    Unconditional on every module-deps return -- PASS, FAIL and ERROR -- for the same
    reason the three notes above are: an explicit `0 resolved` is a different claim
    from a run that resolved some and said nothing, and the exclusions and residual are
    properties of the rules rather than of one verdict.

    The three scopes are the two notes above's, reused rather than re-invented so no
    D8 disclosure can drift from another in what a label means. `_D8_SCOPE_COMPLETE` is
    a real total for the supplied tree; `_D8_SCOPE_PARTIAL` is a run that aborted
    *during* the per-file scan, so both figures are minima established by real
    decisions; `_D8_SCOPE_NOT_STARTED` is a run that aborted *before* the scan began,
    so no edge was ever decided and the zeros record that, never that the tree holds no
    cross-module import. As in the notes above, none of the three borrows ADR-011
    D5.5's PARTIAL/LOWER BOUND or NOT_STARTED coverage vocabulary, which carries the
    coverage pass's different claim.

    `GateReport.notes` is part of `asdict()`, so this one string serves both the text
    and the `--json` surface.
    """
    if scope == _D8_SCOPE_COMPLETE:
        label = "the counts are complete for this run"
    elif scope == _D8_SCOPE_PARTIAL:
        label = ("the counts are NOT FINAL -- this run aborted during the per-file scan, "
                 "so edges in files it never reached are not counted and both figures "
                 "here are minima established by real decisions, not totals")
    elif scope == _D8_SCOPE_NOT_STARTED:
        label = ("the counts are NOT STARTED -- this run aborted before the per-file scan "
                 "began, so no import edge was ever put to the decision and the zeros "
                 "here record that no edge was decided, never that the tree holds no "
                 "cross-module import")
    else:
        raise ValueError(f"unknown ADR-011 D8 import-edge-note scope {scope!r}")
    return (
        f"ADR-011 D8 cross-module import edges: {counts.resolved} edge occurrence(s) "
        f"resolved to a declared module and put to the dependency decision, "
        f"{counts.approved} approved by it and {counts.denied} denied; {label}. An edge "
        "occurrence is one Import/ImportFrom alias target, counted occurrences and not "
        "distinct (importer, target) pairs -- two imports of the same interface are two "
        "-- so the figures reconcile against the violation list rather than against a "
        "deduplicated edge set. APPROVED means the existing decision returned no "
        "violation: a path at or under one of the target module's declared "
        "public_interfaces, or the one TSD §6.3 pinned synchronous direction of a "
        "bidirectional pair; the reserved domain-free modules-root importer '_root' "
        "takes that same unchanged decision, so a root file importing a declared "
        "interface is counted approved. DENIED is resolved minus approved and is every "
        "edge that kept its own unchanged violation: a cross-domain import of another "
        "module's internals or a '_shared' importer depending on a domain module (FAIL "
        "CROSS_DOMAIN_SQL_IMPORT), a '_root' import of a non-interface path (the same "
        "FAIL -- §6.3's pair check is inapplicable there), and a §6.3 reverse edge (FAIL "
        "REVERSE_EDGE_NOT_EVENT_DRIVEN). Counting an edge changed no verdict, no code "
        "and no exit status. EXCLUDED from both figures, because neither is a "
        "cross-module edge the decision was asked about: an import resolving outside the "
        "modules root, a same-module import, and an import of '_shared' as the target "
        "(always allowed and short-circuited before the decision) -- so a nonzero "
        "resolved count is evidence specifically about cross-module edges. An import "
        "target under the modules root naming no declared module contributes to NEITHER "
        "figure: it never resolved to a declared module, it is "
        "MODULE_DEPS_GATE_INPUT_INVALID at exit 2, and counting it approved would "
        "fabricate an approval the decision logic never made. RESIDUAL: statically "
        "resolvable imports only. A dynamic construct refused under ADR-011 D7.1, an "
        "import performed at runtime through importlib or attribute lookup, and anything "
        "outside --modules-dir are examined by nothing here and must not be read as "
        "approved; gate 2 is architecture hygiene, not a security boundary. A nonzero "
        "resolved figure is positive evidence that the cross-module import decision "
        "really ran; an all-zero complete count over a tree means no cross-module edge "
        "existed, so the verdict evidences nothing about import-edge discipline "
        "(GATE2-R1-F12-D8-IMPORT-EDGE-COUNTERS-2026-10-05)"
    )


# --- R1-F12 (GATE2-R1-F12-D8-EXTERNAL-NAMES-2026-10-05): ADR-011 D3.5 + D8 --------
#
# The fourth R1-F12/D8 dimension, and the one ADR-011 words as a disclosure obligation
# rather than only as a counter. D3.5: "Every declared entry is disclosed **by name**,
# with a count, in both text and `--json` output on every run **including PASS**." D8's
# own list says the same thing from the report's side: table references by D3.2 state,
# "with declared external references listed **by name**".
#
# Until this increment the only external-reference figure anywhere on the report was the
# D3.2 state-5 count inside the table-reference attribution note, and that is an
# *observation*: how many identifiers in scanned SQL resolved to a declared entry. It
# answers a different question from the one D3.5 asks. A manifest may declare `audit_log`
# while no scanned statement ever references it -- a legitimate, expected shape -- and the
# state-5 count then reads 0, leaving the declaration itself invisible on the face of the
# report. A reader of a PASS could not see which unowned tables the tree had been
# permitted to reach, which is precisely what makes the field auditable rather than the
# "same bypass wearing a schema field's clothing" D9 rejects.
#
# Three properties this disclosure is built around:
#   * It is a DECLARATION INVENTORY read off the parsed manifest. It never says, and must
#     never be read as saying, that a listed name was encountered in SQL. The
#     observed/attributed state-5 figure stays exactly where it was, and the two notes
#     cross-reference each other so neither can be mistaken for the other.
#   * Identity is the (module, name) PAIR, never the bare name. Two modules may legally
#     declare the same unowned identifier; that is two declarations, listed twice. There
#     is no dedup anywhere on this path.
#   * A run that aborted before a valid manifest existed has NO inventory and says so. A
#     zero-length listing there would be a false claim that the manifest declares nothing.
#     Conversely, once the manifest has parsed the inventory is complete and *stays*
#     complete through a later scan ERROR: it is a property of the input document, not of
#     how far the scan got, so unlike the three counters above this dimension has no
#     partial state at all.


def _declared_external_inventory(
        modules: Mapping[str, ModuleEntry]) -> tuple[tuple[str, str], ...]:
    """ADR-011 D3.5's declaration inventory: every `external_table_references` entry of
    every declared module, as `(module, reference)` pairs.

    Read off the already-parsed `ModuleEntry` tuples rather than re-reading the manifest
    file, so the listing is exactly what `parse_module_manifest` accepted and the rest of
    the run resolves against -- a second read could disagree with it.

    Sorted by `(module, reference)`: the listing must be byte-identical across runs and
    independent of the manifest's JSON key order, so a reader diffing two reports sees a
    real change rather than a reordering. Equal pairs sort adjacent and are both kept.

    Nothing is deduplicated. Two modules declaring the same unowned identifier are two
    entries -- D3.5 forbids an entry *resolving to any module's owned prefix/schema*, not
    two modules naming the same unowned table -- and a value repeated inside one module's
    list is kept too, since `parse_module_manifest` does not reject that repetition and
    collapsing it here would make the report disagree with the manifest on disk."""
    return tuple(sorted(
        (name, ref)
        for name, entry in modules.items()
        for ref in entry.external_table_references
    ))


def _d8_external_declaration_note(inventory: Sequence[tuple[str, str]] | None) -> str:
    """ADR-011 D3.5/D8's declaration disclosure: every manifest-declared
    `external_table_references` entry, by name, with a count, on every run -- PASS, FAIL
    and ERROR alike.

    `inventory` is `None` for a run that aborted before a valid manifest was available,
    and the parsed inventory (possibly empty) otherwise. The two cases are told apart by
    that distinction alone, with no scope label, deliberately: the hazard here is an empty
    listing being read as "the manifest declares nothing", and making "no manifest"
    unrepresentable as a count makes that confusion impossible to introduce by passing the
    wrong label.

    None of the three `_D8_SCOPE_*` labels appears here because there is no partial state
    to label. The inventory is read whole at parse time and never accumulated during the
    scan, so after the manifest parses it is complete and stays complete on a later scan
    ERROR -- the opposite of the three counters above, whose figures a mid-scan abort
    turns into minima. Borrowing their vocabulary would assert a scan-progress claim this
    disclosure does not make.

    `GateReport.notes` is part of `asdict()`, so this one string serves both the text and
    the `--json` surface."""
    if inventory is None:
        body = (
            "NOT STARTED -- declaration count UNKNOWN, declared name(s) UNKNOWN. This run "
            "aborted before a valid manifest was available, so no declaration was ever "
            "read: this is not a report that the manifest declares none, and an empty "
            "inventory must not be inferred from it"
        )
    else:
        declaring = len({name for name, _ in inventory})
        listed = ", ".join(f"{name}:{ref}" for name, ref in inventory) or "none"
        body = (
            f"{len(inventory)} declared entry/ies across {declaring} declaring module(s) "
            f"-- {listed}; the inventory is complete for this run, and stays complete if "
            "the scan later ends in ERROR, being a property of the parsed manifest rather "
            "than of how far the scan got"
        )
    return (
        f"ADR-011 D3.5/D8 declared external_table_references inventory: {body}. Each entry "
        "is listed as module:name and identity is that PAIR, never the bare name: two "
        "modules declaring the same unowned identifier are two entries listed twice, and a "
        "value repeated within one module's list is kept, so nothing here is deduplicated "
        "and the listing reconciles one-to-one against the manifest. Order is sorted by "
        "(module, name), so it is byte-identical across runs and independent of the "
        "manifest's JSON key order. DECLARATION, NOT OBSERVATION: this is what the "
        "manifest declares, and it says nothing about whether any listed name was "
        "encountered in scanned SQL -- a declared entry no statement references is normal "
        "and expected. How many identifiers actually resolved to a declaration is the "
        "separate D3.2 state-5 figure in the table-reference attribution note, so a name "
        "listed here beside a state-5 count of 0 is a consistent pair, never a "
        "contradiction, and one declaration referenced twice makes that figure 2 while "
        "this count stays 1. What is listed here is only ever an identifier no declared "
        "module owns: an entry resolving to ANY module's owned_table_prefixes or "
        "owned_schemas is MODULE_DEPS_GATE_INPUT_INVALID at parse time, because D3.5 makes "
        "the field a declaration and never an exemption -- listing it is what keeps it "
        "auditable instead of a silent manifest-layer allowlist (ADR-011 D9). RESIDUAL: a "
        "listed name is not evidence that the table exists, that anything outside this "
        "manifest approved the dependency, or that reaching it is safe; gate 2 is "
        "architecture hygiene, not a security boundary "
        "(GATE2-R1-F12-D8-EXTERNAL-NAMES-2026-10-05)"
    )


# --- R1-F12 (GATE2-R1-F12-D8-FILE-COUNTS-2026-10-05): ADR-011 D8 file accounting ---
#
# The fifth R1-F12/D8 dimension, and the first item in D8's own list: "files inspected,
# inert, pruned by reason, and at the modules-root". Three of those four figures already
# existed -- but only on the clean path. `N inert file(s)`, `N inspected file(s)` and the
# modules-root count are appended *after* the error-class return, so the two ERROR shapes
# this gate can take carried none of them: a mixed/uninspectable ERROR run and a
# `MODULE_DEPS_GATE_INPUT_INVALID` abort each went out with no file accounting at all,
# which is the condition D8 forbids unqualified by outcome ("Every run, including PASS,
# discloses ..."). The fourth figure, "pruned by reason", existed nowhere: the D5 pass
# counted a single undifferentiated `pruned` aggregate over its top-level listing only,
# and the recursive scan walk counted nothing.
#
# Two conflations this increment deliberately refuses rather than papering over:
#
#   * TOP-LEVEL versus RECURSIVE prunes. The D5 pass prunes immediate children of
#     --modules-dir; `_walk_module` prunes directory entries anywhere inside an
#     already-recognised module or `_shared` subtree. They cover disjoint territory and
#     are reported as two separate by-reason pairs, never summed into one "pruned"
#     figure that would read as a tree-wide total neither traversal establishes.
#   * ATTEMPTED versus INSPECTED files. The existing `N inspected file(s)` figure is
#     `len(checked)`, which is appended *before* the file is read -- true on every
#     non-aborting path, where the two are equal, and an overstatement on exactly the
#     abort path where the figure now matters. So the count the scan commits to and the
#     count whose analysis completed are two fields, and the abort path discloses both.
#
# Reporting only. No file is newly scanned or newly skipped, no prune decision changes,
# and `_walk_module` returns the identical list with or without its counting sink.
#
# --- R1-F12 (GATE2-R1-F12-D8-NAMESPACE-FILE-PRUNE-COUNTS-2026-10-06) ---
#
# The increment above left one traversal out of the file/prune disclosure entirely: the
# ADR-011 D5.2 probe of a *non-discovered* directory under --modules-dir
# (`_scan_namespace_subtree`). The deterministic inspection
# GATE2-R1-F12-D8-NAMESPACE-FILE-PRUNE-INSPECTION-2026-10-06.md reproduced the gap on a
# PASS run: a fixture holding one inert namespace file, one namespace `__pycache__` and
# one namespace dot-directory reported all four of the figures above as 0 and disclosed
# the probe's prunes nowhere, while its inert file surfaced only in the D5 note's own
# inert-namespace bucket. D8 requires "files inspected, inert, pruned by reason, and at
# the modules-root" on every run; those zeros were therefore true of the two traversals
# they name and silent about a third.
#
# This increment adds that third group -- the probe's own by-reason prune pair, its own
# inert figure, and how many directories it probed and short-circuited on -- under the
# same three rules the two pairs above already follow:
#
#   * NEVER SUMMED with either existing pair or with the INERT figure. The probe visits
#     only directories `_discover_modules` dropped, which neither the scan walk nor the
#     D5 top-level listing ever descends into, so the territory is disjoint and the
#     figures are reported side by side rather than folded together.
#   * NOT the D5 pass's independent recursive enumeration. That traversal re-walks the
#     *same* entries the scan walk already pruned, so folding its prunes in would
#     double-count the second pair; it stays excluded, named in the residual.
#   * Establishment state per figure, not one label for the run: UNKNOWN when the
#     top-level listing never ran, an explicit minimum when it ran and did not finish,
#     and an observed zero -- distinguishable from both -- when it finished and reached
#     no non-discovered directory at all.
#
# Reporting only, again: no inclusion, prune, descend or short-circuit decision reads the
# sink, `_scan_namespace_subtree` returns the identical tuple with and without it, the D5
# note's own rendering is untouched, and no verdict, code or exit status changes.


def _d8_file_accounting_note(acct: _FileAccounting, coverage: _CoverageCounts | None,
                             scope: str = _D8_SCOPE_COMPLETE) -> str:
    """ADR-011 D8's file-accounting disclosure: how many files this run inspected,
    attempted, counted inert and found at the modules root, and how many directory
    entries it pruned -- split by reason, and split by which traversal pruned them.
    Three traversals prune, not two
    (GATE2-R1-F12-D8-NAMESPACE-FILE-PRUNE-COUNTS-2026-10-06): the D5 top-level listing,
    the recursive module/`_shared` scan walk, and the D5.2 probe of a non-discovered
    directory, whose own inert files are disclosed here too rather than only in the D5
    coverage note's inert-namespace bucket.

    Unconditional on every module-deps return -- clean verdict, FAIL and both ERROR
    shapes -- for the same reason the four D8 notes above are: an explicit `0 inspected`
    is a different claim from a run that inspected some and said nothing, and the limits
    and residual are properties of the rules rather than of one verdict.

    The three scopes are the four notes above's, reused rather than re-invented so no D8
    disclosure can drift from another in what a label means. `_D8_SCOPE_COMPLETE` is a
    real total for the supplied tree; `_D8_SCOPE_PARTIAL` is a run that aborted *during*
    the per-file scan, so the inspected/attempted/inert figures are minima established by
    real traversal; `_D8_SCOPE_NOT_STARTED` is a run that aborted *before* the scan began,
    so no file was inspected at all and those zeros record that rather than a tree with no
    such file. As in the notes above, none of the three borrows ADR-011 D5.5's
    PARTIAL/LOWER BOUND or NOT_STARTED coverage vocabulary, which carries the coverage
    pass's different claim.

    Two figures carry their own establishment state independently of `scope`, because
    they are established by earlier passes than the per-file scan and a single label
    cannot tell the truth about all four at once. `acct.root_files is None` means
    `_root_level_files` never returned, so the modules-root figure is UNKNOWN rather than
    a zero reading as "the modules root holds no file" -- the same discriminator
    `_d8_external_declaration_note` uses for the manifest. `coverage is None` means the D5
    top-level listing never began, so neither top-level prune reason is reported as zero;
    and `acct.walk_started` is False when no module/`_shared` walk ever ran, so neither
    recursive prune reason is either. When the scan did not complete but those passes did,
    their figures are stated as "at least" -- under-claiming a complete count is the
    fail-closed direction, and over-claiming a partial one is not.

    The namespace-probe group carries a third state the other two do not need. Its
    figures live on the same `coverage` object (the probe runs inside that pass), so
    `coverage is None` is UNKNOWN for the same reason; but once the pass has been
    entered, `coverage.namespace_probes == 0` is an *observed* zero -- the listing looked
    and reached no non-discovered directory -- and says so explicitly, so it can be read
    apart from both the UNKNOWN above and the "at least" minimum a pass that did not
    finish reports. The short-circuit count is disclosed beside the figures because a
    probe stops at its first non-inert file, which makes that directory's figures an
    observation up to that point rather than a subtree total.

    `GateReport.notes` is part of `asdict()`, so this one string serves both the text and
    the `--json` surface."""
    if scope == _D8_SCOPE_COMPLETE:
        label = "the file counts are complete for this run"
    elif scope == _D8_SCOPE_PARTIAL:
        label = ("the file counts are NOT FINAL -- this run aborted during the per-file "
                 "scan, so files it never reached are counted nowhere here and the "
                 "inspected, attempted and inert figures are minima established by real "
                 "traversal, not totals")
    elif scope == _D8_SCOPE_NOT_STARTED:
        label = ("the file counts are NOT STARTED -- this run aborted before the per-file "
                 "scan began, so no file was ever inspected and the inspected, attempted "
                 "and inert zeros record that no scan happened, never that the tree holds "
                 "no such file")
    else:
        raise ValueError(f"unknown ADR-011 D8 file-accounting-note scope {scope!r}")
    root = "UNKNOWN" if acct.root_files is None else str(acct.root_files)
    if coverage is None:
        top = ("UNKNOWN '__pycache__' and UNKNOWN dot-prefixed directory prune(s) -- the "
               "top-level listing never ran, so neither reason is reported as zero")
    else:
        top_state = ("at least this many -- the top-level listing did not finish"
                     if scope == _D8_SCOPE_NOT_STARTED else
                     "the by-reason split of the single aggregate the ADR-011 D5 coverage "
                     "note reports, one producer for both surfaces")
        top = (f"{coverage.pruned_pycache} '__pycache__' and {coverage.pruned_dot} "
               f"dot-prefixed directory prune(s) ({top_state})")
    if not acct.walk_started:
        walk = ("UNKNOWN '__pycache__' and UNKNOWN dot-prefixed directory prune(s) -- no "
                "module or _shared walk ever ran, so neither reason is reported as zero")
    else:
        walk_state = ("at least this many -- the walk did not finish"
                      if scope == _D8_SCOPE_NOT_STARTED else "complete")
        walk = (f"{acct.walk_pruned_pycache} '__pycache__' and {acct.walk_pruned_dot} "
                f"dot-prefixed directory prune(s) ({walk_state})")
    # R1-F12 / ADR-011 D8
    # (GATE2-R1-F12-D8-NAMESPACE-FILE-PRUNE-COUNTS-2026-10-06): the third traversal's
    # group. `coverage is None` is the same UNKNOWN discriminator the top-level pair
    # uses -- the probe runs inside that very pass, so a run that never entered it
    # never probed anything either, and a zero here would read as "no non-discovered
    # directory exists". When the pass was entered, `namespace_probes == 0` is a real
    # observed zero (it looked and found no such directory) and is labelled as one, so
    # it cannot be confused with the UNKNOWN above or with the minimum below.
    if coverage is None:
        namespace = ("UNKNOWN '__pycache__' and UNKNOWN dot-prefixed directory prune(s), "
                     "UNKNOWN inert file(s) across UNKNOWN probed director(y/ies), of "
                     "which UNKNOWN stopped at a first non-inert file -- the top-level "
                     "listing never ran, so no non-discovered directory was ever probed "
                     "and no figure here is reported as zero")
    else:
        if scope == _D8_SCOPE_NOT_STARTED:
            ns_state = ("at least this many -- the top-level listing did not finish, so a "
                        "non-discovered directory it never reached is counted nowhere here")
        elif coverage.namespace_probes == 0:
            ns_state = ("complete -- the top-level listing finished and reached no "
                        "non-discovered directory at all, so these are observed zeros "
                        "rather than figures no pass ever established")
        else:
            ns_state = "complete"
        namespace = (
            f"{coverage.namespace_probe_pruned_pycache} '__pycache__' and "
            f"{coverage.namespace_probe_pruned_dot} dot-prefixed directory prune(s), "
            f"{coverage.namespace_probe_inert} inert file(s) across "
            f"{coverage.namespace_probes} probed director"
            f"{'y' if coverage.namespace_probes == 1 else 'ies'}, of which "
            f"{coverage.namespace_probe_short_circuited} stopped at a first non-inert "
            f"file ({ns_state})")
    return (
        f"ADR-011 D8 file accounting: {acct.inspected} file(s) INSPECTED -- opened, "
        f"reduced to statements/tokens and carried to the end of their own analysis; "
        f"{acct.attempted} ATTEMPTED -- substantive file(s) the scan committed to opening, "
        f"the same figure as the report's checked list; {acct.inert} INERT file(s) counted "
        f"and never scanned (.md/.txt/.gitkeep); {root} file(s) AT THE MODULES ROOT, "
        f"walked as the domain-free {ROOT_IMPORTER!r} importer (ADR-011 D4). PRUNED BY "
        f"REASON, in three separate pairs -- top-level listing of --modules-dir's immediate "
        f"children: {top}; recursive module/_shared scan walk: {walk}; "
        f"non-discovered-namespace probe: {namespace}. {label}. ATTEMPTED "
        "IS NOT INSPECTED: the two are equal on every path that does not abort -- an "
        "uninspectable finding, an unattributed identifier and a real violation each leave "
        "the scan running -- and diverge by exactly the file the run aborted on, which is "
        "the only file the scan opened without finishing. A nonzero attempted figure beside "
        "a smaller inspected one is therefore the abort itself, never a silent skip, and "
        "the inspected figure is the one a clean verdict's self-evidence rests on. THE "
        "THREE PRUNE PAIRS ARE NEVER SUMMED: they count different entries over disjoint "
        "territory -- the first, immediate children of --modules-dir refused by the "
        "independent ADR-011 D5 coverage pass before discovery; the second, directory "
        "entries the scan walk refused at any depth inside an already-discovered module or "
        "_shared subtree; the third, directory entries the ADR-011 D5.2 probe refused at "
        "any depth inside a NON-discovered directory under --modules-dir -- territory the "
        "other two traversals never descend into, since that directory has no "
        "__init__.py and discovery dropped it. None of the three is a tree-wide total, and "
        "adding them would assert a tree-wide figure this gate does not establish. The two "
        "reasons within each pair "
        "are disjoint by construction, since '__pycache__' does not begin with a dot, so "
        "each pair's sum is exactly that traversal's own prune count. RECONCILIATION: "
        "inspected + inert is the substantive/inert partition of every file the walks "
        "yielded, inspected is at most attempted, and the modules-root figure is the scan "
        "surface's own count of the same bucket the ADR-011 D5 coverage note counts "
        "independently -- the two are reconciled by D5.1's two-direction set diff, which "
        "makes a disagreement ERROR MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH rather than a "
        "silent pass, so they are deliberately two figures and not one. THE "
        "NON-DISCOVERED-NAMESPACE INERT FIGURE IS NOT PART OF THE INERT FIGURE AND MUST "
        "NEVER BE ADDED TO IT: the INERT figure counts inert files the module/_shared/"
        "modules-root walks yielded, the namespace figure counts inert files inside "
        "directories those walks never reach, so each is its own traversal's count. On a "
        "run where no non-discovered directory held a non-inert file it is the same figure "
        "the ADR-011 D5 coverage note's inert-namespace bucket reports; on a run where one "
        "did, that bucket credits nothing for that directory while this figure keeps what "
        "the probe had already seen, which is why the probe's own figure is disclosed here "
        "rather than left to that bucket. RESIDUAL -- not "
        "counted by any figure here and not to be read as examined: a pruned directory's "
        "CONTENTS at any depth, since a pruned entry is never descended into, so no file "
        "count exists behind any of the three prune pairs; everything at or below a "
        "namespace probe's short-circuit point, since that probe stops at the first "
        "non-inert file -- the one witness the ERROR needs -- and never enumerates the "
        "rest of that directory, so its figures for a short-circuited directory are "
        "observations up to that point and never a subtree total; prunes made by the D5 "
        "pass's own independent recursive enumeration of an already-discovered module or "
        "_shared subtree, which re-traverses the same entries the scan walk already pruned "
        "and whose prunes would double-count the second pair if folded in; every file "
        "outside --modules-dir; and the text "
        "inside an inspected file that the SQL trigger, the D6.4 docstring exclusion or "
        "D7.1 kept from the scanner, which the four D8 notes above account for per subject "
        "rather than per file. An inspected file is evidence that this gate read and parsed "
        "it, never that the file is safe: gate 2 is architecture hygiene, not a security "
        "boundary (GATE2-R1-F12-D8-FILE-COUNTS-2026-10-05, extended by "
        "GATE2-R1-F12-D8-NAMESPACE-FILE-PRUNE-COUNTS-2026-10-06)"
    )


# --- R1-F09 (GATE2-R1-F09-D72-MIXED-REPORT-2026-10-05): ADR-011 D7.2 partitioning --


def _partition_codes(violations: Sequence[Violation]) -> str:
    return ", ".join(sorted({v.code for v in violations})) or "none"


def _d72_partition_note(fail_class: Sequence[Violation],
                        error_class: Sequence[Violation]) -> str:
    """ADR-011 D7.2's disclosure for the ERROR report that carries both partitions.

    Emitted on every ERROR return from the scan, including when `fail_class` is
    empty: an explicit "0 FAIL-class" count is exactly what lets a reader tell
    "none were found" apart from R1-F09's old behaviour, where some *were* found
    and then silently dropped. Keeping the note unconditional also keeps the
    ERROR report's note shape stable across the uninspectable-only and mixed
    runs, so a corpus can assert on it without branching.

    Exit 2 on a mixed run must never be read as "no cross-domain violation was
    found": the ERROR-class findings mean the scan did not complete, so the
    FAIL-class partition is a lower bound, not an exhaustive verdict.
    """
    return (
        f"ADR-011 D7.2 partitioned report: {len(fail_class)} FAIL-class violation(s) "
        f"[{_partition_codes(fail_class)}] listed first, then {len(error_class)} "
        f"ERROR-class finding(s) [{_partition_codes(error_class)}]; status is ERROR at "
        "exit 2 because the ERROR-class findings mean the scan did not complete, so the "
        "FAIL-class partition is a lower bound, not an exhaustive verdict -- exit 2 here "
        "does not mean zero FAIL-class violations were found "
        "(GATE2-R1-F09-D72-MIXED-REPORT-2026-10-05)"
    )


def _d74_dedupe_order(violations: Sequence[Violation]) -> list[Violation]:
    """ADR-011 D7.4 (R2-N03 / R1-F15 / R1-F20): exact-key deduplication plus
    deterministic ordering by `(code, subject, detail)`, first-seen row
    preserved within a key.

    `setdefault` rather than assignment is the first-seen half: the retained
    object is the one the scanner produced first for that key, so any
    identity-bearing or future per-occurrence metadata on `Violation` survives
    the collapse instead of being overwritten by the last duplicate. Today
    `Violation` is a frozen three-field record whose fields *are* the key, so
    duplicates are equal and the distinction is observable only as object
    identity -- which is exactly why it is pinned here rather than left to the
    dict's incidental behaviour.

    Deliberately distinct from `_dedupe_coverage_violations`, which keeps its
    own narrower contract (last-seen row, ordered by `subject` alone) for the
    single coverage ERROR code; the two are not merged, so neither helper's
    behaviour is changed by the other.

    Applied per list, never across lists, so ADR-011 D7.2's FAIL-class-then-
    ERROR-class partitioning and the disjointness of the D7.1 ERROR codes are
    untouched. Ordering only -- no row is reclassified, no status or exit code
    is derived from it, and the D8 counters are accumulated by the scanner
    independently of these lists.
    """
    seen: dict[tuple[str, str, str], Violation] = {}
    for v in violations:
        seen.setdefault((v.code, v.subject, v.detail), v)
    return sorted(seen.values(), key=lambda v: (v.code, v.subject, v.detail))


def run_module_deps_gate(modules_dir: Path = DEFAULT_MODULES_DIR,
                         manifest_path: Path = DEFAULT_MODULE_MANIFEST) -> GateReport:
    # ADR-011 D5.5/D8: accumulated outside the try, so whatever disclosure the
    # run had already established survives into the ERROR report built by the
    # `except GateInputError` handler below instead of being discarded with the
    # frame. Empty when the failure precedes any disclosure.
    notes: list[str] = []
    # ADR-011 D5.5: True once the reconciliation pass has completed and its
    # complete disclosure is in `notes`. Together with `exc.notes` (non-empty
    # only when the pass itself aborted) this is the exact discriminator for
    # "no coverage disclosure exists yet", which is the pre-coverage shape.
    coverage_disclosed = False
    # R1-F10 / ADR-011 D6.4: how many docstring positions this run withheld from the
    # SQL scan. Accumulated outside the try for the same reason `notes` is -- the
    # count (and its residual disclosure) must survive into the ERROR report built by
    # the `except GateInputError` handler below instead of being discarded with the
    # frame, which is R1-F09's dropped-disclosure failure mode.
    docstrings_excluded = 0
    # R1-F11 / ADR-011 D6.2: how many `bytes` literals this run decoded and scanned,
    # and how many no codec could decode. Accumulated outside the try for the same
    # reason `docstrings_excluded` is -- the counts and their residual must survive
    # into the ERROR report rather than being discarded with the frame.
    bytes_literals_scanned = 0
    bytes_literals_undecodable = 0
    # R1-F12 / ADR-011 D8: how many text subjects this run's SQL scanner recognised as a
    # SQL statement and therefore examined for table positions. Accumulated outside the
    # try for the same reason the counters above are -- the count must survive into the
    # ERROR report rather than being discarded with the frame, where its scope is
    # labelled NOT FINAL or NOT STARTED rather than read as a total.
    sql_trigger_subjects = 0
    # R1-F12 / ADR-011 D8/D3.2: table references by attribution state, mutated in place
    # by `_scan_sql_text`. Constructed outside the try for the same reason the counters
    # above are -- the states this run really attributed must survive into the ERROR
    # report, labelled a minimum (or never-started) rather than discarded with the frame.
    table_refs = _TableRefCounts()
    # R1-F12 / ADR-011 D6.3+D8: the zero-table partition of the recognised subjects --
    # clean (no table position at all) kept apart from the two fail-closed classes.
    # Constructed outside the try for the same reason the counters above are.
    zero_table = _ZeroTableCounts()
    # R2-N01 / ADR-011 D6.8.6: how many table-position signals this run suppressed as
    # privilege-list tokens, aggregated across every subject the scanner receives.
    # Constructed outside the try for the same reason the counters above are, and for
    # one more that is specific to this dimension: D6.8 removes refusal surface, so an
    # ERROR report that dropped the figure would be the one report where a reader most
    # needs to know the gate chose not to look at something.
    suppression = _SuppressionCounts()
    # R1-F12 / ADR-011 D8: cross-module import edges resolved and approved, accumulated
    # by the import branch below. Constructed outside the try for the same reason the
    # counters above are -- the edges this run really decided must survive into the
    # ERROR report, labelled a minimum (or never-decided) rather than discarded.
    import_edges = _ImportEdgeCounts()
    # R1-F12 / ADR-011 D3.5+D8: the manifest's `external_table_references` declaration
    # inventory. `None` until a manifest has actually parsed, which is the whole point --
    # an ERROR raised before that point must disclose UNKNOWN rather than an empty listing
    # that would read as "the manifest declares none". Set once, immediately after the
    # parse, and never mutated by the scan: unlike the counters above this is a property of
    # the input document, so it is complete from that moment on and a later scan ERROR
    # neither shrinks it nor makes it a minimum.
    declared_external: tuple[tuple[str, str], ...] | None = None
    # R1-F12 / ADR-011 D8: files inspected / attempted / inert / at the modules root, plus
    # the recursive scan walk's prunes by reason. Constructed outside the try for the same
    # reason the counters above are -- D8 requires the file accounting on EVERY run, and
    # until this increment both ERROR returns went out carrying none of it.
    acct = _FileAccounting()
    # R1-F12 / ADR-011 D8: the D5 pass's own top-level prune counters, by reason. `None`
    # until the pass is actually entered, which is the discriminator that keeps a run
    # aborting upstream of it from reporting a prune count of zero it never established.
    # The object is handed to `_reconcile_module_coverage` as a sink rather than
    # recomputed, so the D8 split and the D5 aggregate have exactly one producer.
    coverage_counts: _CoverageCounts | None = None
    try:
        modules_root = _modules_root_package(modules_dir)
        modules, default_schema = load_module_manifest(manifest_path, modules_root, modules_dir)
        declared_external = _declared_external_inventory(modules)
        discovered = _discover_modules(modules_dir)
        undeclared = sorted(set(discovered) - set(modules))
        if undeclared:
            raise GateInputError(f"discovered module(s) with no manifest entry: {undeclared}")
        no_dir = sorted(set(modules) - set(discovered))
        notes += [f"{len(modules)} declared module(s)", f"{len(discovered)} scanned module(s)"]
        if no_dir:
            notes.append(f"manifest entries with no directory: {no_dir}")

        # R1-F12 / ADR-011 D8: `acct` is the walk's prune-by-reason counting sink and
        # nothing else -- the file list each call returns is unchanged.
        scan_units: list[tuple[str, list[Path]]] = [
            (name, _walk_module(modules_dir / name, acct)) for name in discovered
        ]
        shared_dir = modules_dir / SHARED_PACKAGE
        shared_present = shared_dir.is_dir() and not shared_dir.is_symlink()
        if shared_present:
            scan_units.append((SHARED_PACKAGE, _walk_module(shared_dir, acct)))
        # ADR-011 D4 (GATE2-R1-D4-ROOT-FILE-SCAN-2026-10-05): files directly under
        # --modules-dir are scanned as the reserved, domain-free _root importer. This
        # unit always runs, even when it yields zero files.
        root_files = _root_level_files(modules_dir)
        # R1-F12 / ADR-011 D8: set only once the listing has really returned, so a run
        # that aborted upstream discloses UNKNOWN rather than a modules-root zero.
        acct.root_files = len(root_files)
        scan_units.append((ROOT_IMPORTER, root_files))

        # ADR-011 D5 (GATE2-R1-D5-NAMESPACE-COVERAGE, R1-F04): a second, independent
        # enumeration of --modules-dir reconciled against the discovery above -- a
        # directory with no __init__.py (a fully importable PEP 420 namespace
        # package) that _discover_modules silently dropped is caught here as
        # MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH rather than vanishing from the scan.
        # ADR-011 D5.1 recursive coverage reconciliation: the real walked-path union
        # already assembled above (scan_units) is passed in as-is -- never
        # recomputed inside _reconcile_module_coverage -- so its own independent
        # recursive enumeration can diff against what was actually walked.
        walked_paths: set[Path] = {path for _, files in scan_units for path in files}
        # R1-F12 / ADR-011 D8: assigned immediately before the call, so `None` means the
        # pass was never entered and a nonzero/zero prune split means it was.
        coverage_counts = _CoverageCounts()
        coverage_violations, coverage_notes = _reconcile_module_coverage(
            modules_dir, set(discovered), shared_present, walked_paths, coverage_counts
        )
        notes += coverage_notes
        coverage_disclosed = True

        violations: list[Violation] = []
        uninspectable: list[Violation] = []
        unattributed: list[Violation] = []
        checked: list[str] = []
        substantive_any = False

        for importer, files in scan_units:
            for path in files:
                relpath = path.relative_to(modules_dir).as_posix()
                kind = _categorize(path)
                if kind == "inert":
                    # R1-F12 / ADR-011 D8: the inert tally lives on `acct` rather than in
                    # a local, so the figure the clean path has always reported and the
                    # one the two ERROR paths now report have a single producer.
                    acct.inert += 1
                    continue
                checked.append(relpath)
                # R1-F12 / ADR-011 D8: attempted is incremented here, with
                # `checked.append`, and inspected only once this file's own analysis
                # completes below -- the pair is what makes an aborting run's figures
                # readable as "opened N, finished N-1" instead of overstating either.
                acct.attempted += 1
                # R1-F07 / ADR-011 D7.3: both reads below go through the one
                # conversion helper, so an unreadable or non-UTF-8 `.py` *or* `.sql`
                # file ends as MODULE_DEPS_GATE_INPUT_INVALID ERROR at exit 2 with a
                # report on both surfaces, not as an uncaught UnicodeDecodeError at
                # exit 1 with none.
                if kind == "sql":
                    # substantive is set only after the read succeeds: a file whose
                    # bytes could not be decoded was never scanned, so it must not
                    # also count as evidence that something was inspected.
                    text = _read_source_text(path, relpath, kind)
                    substantive_any = True  # every readable .sql file is substantive
                    # R1-F12 / ADR-011 D8: counted only when the scanner's own trigger
                    # fired, here and at both literal call sites below.
                    sql_trigger_subjects += int(_scan_sql_text(
                        text, importer, modules, relpath, default_schema,
                        violations, uninspectable, unattributed, table_refs,
                        zero_table, suppression,
                    ))
                    # R1-F12 / ADR-011 D8: the `.sql` file's whole analysis is that one
                    # scan call, so reaching here is this file's completed inspection.
                    acct.inspected += 1
                    continue
                source = _read_source_text(path, relpath, kind)
                try:
                    tree = ast.parse(source, filename=str(path))
                except (SyntaxError, ValueError) as exc:
                    raise GateInputError(f"{relpath}: cannot parse ({exc})") from None
                if _is_substantive(tree):
                    substantive_any = True
                package = _file_package_info(path.relative_to(modules_dir), modules_root)
                # R1-F05: resolved once per file, before the node walk, so a call of a
                # name bound by `from importlib import import_module [as ...]` -- or a
                # dynamic import on a receiver bound by `import builtins [as ...]` /
                # `import importlib [as ...]`, or an `exec` bound by
                # `from builtins import exec [as ...]` -- is
                # recognised regardless of where the call sits relative to the import.
                dynamic_names = _dynamic_import_bindings(tree)
                builtins_names = _builtins_module_bindings(tree)
                importlib_names = _importlib_module_bindings(tree)
                exec_names = _exec_bindings(tree)
                # R1-F06: likewise resolved once per file, so the fragment-sequence
                # branch can tell a bare sequence display from one the `.join` branch
                # already reports, which `ast.walk` cannot (it yields nodes with no
                # parent link).
                join_argument_ids = _join_argument_sequences(tree)
                # R1-F10 / ADR-011 D6.4: likewise resolved once per file, and keyed on
                # `id()` for the same reason -- `ast.walk` yields nodes with no parent
                # link, so a docstring position cannot be recognised from the node
                # alone, and recognising it by string *value* would suppress every
                # byte-identical executable literal in the same file.
                docstring_ids = _docstring_constant_ids(tree)
                for node in ast.walk(tree):
                    uninspectable += _uninspectable_for_node(node, relpath, dynamic_names,
                                                             builtins_names, importlib_names,
                                                             exec_names, join_argument_ids)
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        for resolved, lineno in _import_targets(node, package, relpath):
                            if not resolved.startswith(modules_root + "."):
                                continue
                            remainder = resolved[len(modules_root) + 1:]
                            target = remainder.split(".", 1)[0]
                            # R1-F12 / ADR-011 D8: both short-circuits above and this one
                            # stay out of the edge count entirely -- an import resolving
                            # outside the modules root, a same-module import and an
                            # import of `_shared` as target are not cross-module edges
                            # the decision is asked about, so folding them in would
                            # inflate `resolved` with occurrences nothing decided.
                            if target == importer or target == SHARED_PACKAGE:
                                continue
                            if target not in modules:
                                # Counted in neither figure, deliberately: this target
                                # never resolved to a declared module, so there is no
                                # edge for the decision to approve, and incrementing
                                # `approved` (or even `resolved`) here would fabricate an
                                # approval on the exact path that fails closed at exit 2.
                                raise GateInputError(
                                    f"{relpath}:{lineno}: import target {resolved!r} does not "
                                    "resolve to a declared module or '_shared'"
                                )
                            import_edges.resolved += 1
                            viol = _import_violation(importer, target, resolved, relpath,
                                                     lineno, modules)
                            if viol:
                                violations.append(viol)
                            else:
                                # The decision's own clean outcome -- an approved
                                # public_interfaces path, or the one pinned §6.3
                                # synchronous direction -- read off `_import_violation`'s
                                # existing return rather than re-derived, so the
                                # disclosure cannot disagree with the verdict.
                                import_edges.approved += 1
                    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                        # R1-F10 / ADR-011 D6.4: a docstring position is withheld from
                        # the SQL scan and counted -- never silently dropped. Every
                        # other string literal, leading or not, still reaches
                        # `_scan_sql_text` unchanged.
                        if id(node) in docstring_ids:
                            docstrings_excluded += 1
                        else:
                            sql_trigger_subjects += int(_scan_sql_text(
                                node.value, importer, modules, f"{relpath}:{node.lineno}",
                                default_schema, violations, uninspectable, unattributed,
                                table_refs, zero_table, suppression,
                            ))
                    elif isinstance(node, ast.Constant) and isinstance(node.value, bytes):
                        # R1-F11 / ADR-011 D6.2: a `bytes` literal is decoded and fed to
                        # the same `_scan_sql_text`; until this increment the `str`-only
                        # test above skipped it outright, so `b"SELECT a FROM
                        # bil_invoices"` came back clean. No docstring check here, by
                        # design: `_docstring_constant_ids` collects `str` nodes only
                        # because Python binds only a `str` `body[0]` to `__doc__`, so a
                        # `bytes` literal in that position is executable text, not a
                        # docstring, and D6.4's exclusion must not reach it.
                        decoded = _decode_bytes_literal(node.value)
                        if decoded is None:
                            bytes_literals_undecodable += 1
                            uninspectable.append(Violation(
                                "MODULE_DEPS_SOURCE_UNINSPECTABLE",
                                f"{relpath}:{node.lineno}",
                                "bytes literal could not be decoded by any of "
                                f"{list(_BYTES_LITERAL_CODECS)}, so its SQL could not be "
                                "reduced to statements/tokens (ADR-011 D6.2)",
                            ))
                        else:
                            bytes_literals_scanned += 1
                            # R1-F12 / ADR-011 D8: a decoded bytes literal is a scanner
                            # subject like any other, so it contributes to the trigger
                            # count on exactly the same condition. An *undecodable* one
                            # took the branch above and never reached the scanner, so it
                            # contributes nothing here -- it is disclosed by the D6.2
                            # note's own undecodable count instead.
                            sql_trigger_subjects += int(_scan_sql_text(
                                decoded, importer, modules, f"{relpath}:{node.lineno}",
                                default_schema, violations, uninspectable, unattributed,
                                table_refs, zero_table, suppression,
                            ))
                # R1-F12 / ADR-011 D8: the node walk above is this `.py` file's whole
                # analysis, so reaching here -- after every node, and only if none of
                # them raised -- is its completed inspection. An uninspectable finding
                # or a real violation does not prevent it: the file was fully examined,
                # which is exactly what distinguishes this figure from `attempted`.
                acct.inspected += 1
    except GateInputError as exc:
        # ADR-011 D5.5/D8: an ERROR run discloses the bucket counts it did
        # establish, in both text and --json (GateReport.notes is part of
        # asdict(), so one list serves both surfaces). `exc.notes` carries the
        # partial, lower-bound-labelled coverage disclosure when the failure
        # happened *inside* the coverage enumeration; `notes` carries whatever
        # complete disclosure preceded a later failure. Status and exit code
        # are untouched -- ERROR at exit 2, fail-closed (D7).
        #
        # Third case: the failure preceded the coverage pass entirely (absent /
        # symlinked / `__init__.py`-less --modules-dir, unusable manifest,
        # undeclared discovered module), so neither source carries disclosure
        # and the report used to go out note-blind. `_pre_coverage_notes` states
        # that truthfully -- NOT_STARTED/UNKNOWN buckets, never zeros.
        disclosure = exc.notes
        if not coverage_disclosed and not disclosure:
            disclosure = _pre_coverage_notes()
        #
        # R1-F10 / ADR-011 D6.4: the docstring-exclusion count and its residual go out
        # on this path too, labelled NOT FINAL because the scan aborted. Dropping a
        # disclosure on the ERROR path specifically is R1-F09's own failure mode.
        #
        # R1-F12 / ADR-011 D8: likewise for the SQL-trigger inspection count, but with
        # the two abort shapes told apart rather than both labelled NOT FINAL.
        # `coverage_disclosed` flips immediately before the per-file scan loop, so it is
        # the exact discriminator: False means the loop never ran and the 0 records that
        # nothing was inspected; True means the loop ran and the count is a real minimum.
        return GateReport("module-deps", ERROR,
                          [Violation("MODULE_DEPS_GATE_INPUT_INVALID", "-", str(exc))],
                          [], notes + disclosure
                          + [_d64_docstring_note(docstrings_excluded, partial=True),
                             _d62_bytes_note(bytes_literals_scanned,
                                             bytes_literals_undecodable, partial=True),
                             _d8_trigger_note(
                                 sql_trigger_subjects,
                                 _D8_SCOPE_PARTIAL if coverage_disclosed
                                 else _D8_SCOPE_NOT_STARTED),
                             # R1-F12 / ADR-011 D8/D3.2: the attribution-state counts go
                             # out on this path too, under the same discriminator and
                             # the same three-way labelling -- so an aborted run's
                             # figures can never be read as a total, and a pre-scan abort
                             # discloses "no attribution happened" rather than a clean
                             # zero.
                             _d8_table_ref_note(
                                 table_refs,
                                 _D8_SCOPE_PARTIAL if coverage_disclosed
                                 else _D8_SCOPE_NOT_STARTED),
                             # R2-N01 / ADR-011 D6.8.6: and the privilege-list
                             # suppression count, under the same discriminator and the
                             # same three-way labelling. It goes out on the ERROR path
                             # for the reason D6.8.6 gives for requiring it at all: a
                             # narrowing that leaves no trace in the report cannot be
                             # told from silent under-extraction, and an aborted run is
                             # where that confusion would do the most damage. The label
                             # also restates, on every scope, that the table-reference
                             # figure stays a D6.7.5 lower bound.
                             _d68_suppression_note(
                                 suppression,
                                 _D8_SCOPE_PARTIAL if coverage_disclosed
                                 else _D8_SCOPE_NOT_STARTED),
                             # R1-F12 / ADR-011 D6.3+D8: and the zero-table partition,
                             # under the same discriminator and the same three-way
                             # labelling -- so an aborted run can neither read its clean
                             # zero-table figure as a total nor let a pre-scan abort's
                             # zero read as "the tree holds no table-free statement".
                             _d8_zero_table_note(
                                 zero_table,
                                 _D8_SCOPE_PARTIAL if coverage_disclosed
                                 else _D8_SCOPE_NOT_STARTED),
                             # R1-F12 / ADR-011 D8: and the cross-module import-edge
                             # counts, under the same discriminator and the same
                             # three-way labelling. The undeclared-target abort is
                             # itself raised from the import branch, so this path must
                             # disclose the edges decided *before* it as a minimum
                             # rather than claim a total or report nothing.
                             _d8_import_edge_note(
                                 import_edges,
                                 _D8_SCOPE_PARTIAL if coverage_disclosed
                                 else _D8_SCOPE_NOT_STARTED),
                             # R1-F12 / ADR-011 D3.5+D8: and the declared-external
                             # inventory, which is deliberately NOT labelled by
                             # `coverage_disclosed`. `declared_external` is `None` exactly
                             # when no manifest had parsed yet (disclosed UNKNOWN, never a
                             # false zero) and the complete inventory in every other case,
                             # including an abort during or after the scan -- the manifest
                             # does not become less parsed because a later file failed.
                             _d8_external_declaration_note(declared_external),
                             # R1-F12 / ADR-011 D8: and the file accounting, under the
                             # same discriminator and the same three-way labelling. Both
                             # the modules-root figure and the two prune pairs carry
                             # their own UNKNOWN state inside the note, because each is
                             # established by an earlier pass than the per-file scan and
                             # a run can abort between any two of them -- so this path
                             # discloses exactly which of the four were reached rather
                             # than one label for all of them.
                             _d8_file_accounting_note(
                                 acct, coverage_counts,
                                 _D8_SCOPE_PARTIAL if coverage_disclosed
                                 else _D8_SCOPE_NOT_STARTED)])

    # R2-N03 / ADR-011 D7.4: applied once here, after the scan and before either
    # remaining return, so the ERROR path and the FAIL/PASS path emit the same deduped,
    # `(code, subject, detail)`-ordered rows. Per list, so D7.2's partition order below
    # survives; `coverage_violations` is deliberately excluded -- it keeps its own
    # narrower `_dedupe_coverage_violations` contract, already applied upstream.
    # Nothing downstream re-derives status, exit code or a D8 counter from these lists,
    # so this is an emission-ordering change only.
    violations = _d74_dedupe_order(violations)
    uninspectable = _d74_dedupe_order(uninspectable)
    unattributed = _d74_dedupe_order(unattributed)

    # ADR-011 D7.1: MODULE_DEPS_SOURCE_UNINSPECTABLE and MODULE_DEPS_TABLE_UNATTRIBUTED
    # are disjoint ERROR codes (the discriminator is whether extraction succeeded), but
    # both are ERROR/exit 2 -- reported together, never collapsed into one code, so an
    # acceptance corpus can still assert the exact code on each row.
    #
    # R1-F09 / ADR-011 D7.2 (GATE2-R1-F09-D72-MIXED-REPORT-2026-10-05): a *mixed* run
    # now carries the FAIL-class `violations` it had already collected into this same
    # ERROR report, partitioned -- FAIL-class first, then ERROR-class, each partition
    # in its own unchanged collection order. Until this increment `violations` was
    # dropped on the floor here, so a single uninspectable construct anywhere in the
    # tree suppressed every real CROSS_DOMAIN_SQL_IMPORT / REVERSE_EDGE_NOT_EVENT_DRIVEN
    # already found in the same run, from both the text and the --json surface.
    #
    # Reporting change only: nothing is newly detected, nothing is reclassified, and
    # the scanner is untouched. The run's status stays ERROR at exit 2 (fail-closed --
    # an incomplete scan must not be able to downgrade itself to a mere FAIL just
    # because it also found something real), and `checked` stays the same sorted list.
    # R1-F10 / ADR-011 D6.4: appended here, after the scan and before either remaining
    # return, so the count and its residual are reported identically whether the run
    # ends ERROR, FAIL or PASS -- the residual is a property of the rule, not of the
    # verdict.
    notes.append(_d64_docstring_note(docstrings_excluded))
    # R1-F11 / ADR-011 D6.2: appended at the same point, and for the same reason -- the
    # bytes counts and their residual are reported identically on the ERROR, FAIL and
    # clean paths, since the residual is a property of the rule, not of the verdict.
    notes.append(_d62_bytes_note(bytes_literals_scanned, bytes_literals_undecodable))
    # R1-F12 / ADR-011 D8: appended at the same point, and for the same reason -- the
    # trigger-recognition count is the clean verdict's own self-evidence, and it is
    # reported identically on the ERROR, FAIL and clean paths. Reaching here means the
    # per-file scan completed, so the scope is the complete one.
    notes.append(_d8_trigger_note(sql_trigger_subjects))
    # R1-F12 / ADR-011 D8/D3.2: and the per-identifier attribution-state counts, at the
    # same point and for the same reason -- they are what makes a clean verdict evidence
    # that the *ownership decision* ran, not merely that the scanner recognised text,
    # and they are reported identically on the ERROR, FAIL and clean paths. Reaching
    # here means the per-file scan completed, so the scope is the complete one.
    notes.append(_d8_table_ref_note(table_refs))
    # R2-N01 / ADR-011 D6.8.6: and the privilege-list suppression count, appended
    # immediately after the figure it qualifies and on every path for the same reason --
    # D6.8.6 requires it "on every run including PASS", and PASS is the path where it
    # matters most, since a suppressed signal leaves no violation and no table reference
    # behind and this note is then the only evidence the narrowing ran. Reaching here
    # means the per-file scan completed, so the scope is the complete one.
    notes.append(_d68_suppression_note(suppression))
    # R1-F12 / ADR-011 D6.3+D8: and the zero-table partition of those same recognised
    # subjects, at the same point and for the same reason -- it is what tells a reader
    # that a triggered subject with no table position was examined and found clean
    # (D6.3's explicit clean case) rather than refused as unresolvable, which the two
    # notes above cannot distinguish. Reaching here means the per-file scan completed,
    # so the scope is the complete one.
    notes.append(_d8_zero_table_note(zero_table))
    # R1-F12 / ADR-011 D8: and the cross-module import-edge counts, at the same point
    # and for the same reason -- they are the import half of what a clean verdict
    # claims, where the two notes above cover only SQL text, and they are reported
    # identically on the ERROR, FAIL and clean paths. Reaching here means the per-file
    # scan completed, so the scope is the complete one.
    notes.append(_d8_import_edge_note(import_edges))
    # R1-F12 / ADR-011 D3.5+D8: and the declared-external inventory, at the same point and
    # for the same reason -- D3.5 requires every declared entry by name with a count on
    # every run *including PASS*, and the ERROR, FAIL and clean paths must disclose it
    # identically. Reaching here means the manifest parsed, so the inventory is never
    # `None` on this path; the note's own `None` branch exists for the aborted-before-parse
    # return above, not for this one.
    notes.append(_d8_external_declaration_note(declared_external))
    # R1-F12 / ADR-011 D8: and the file accounting, at the same point and for the same
    # reason -- D8's own list opens with "files inspected, inert, pruned by reason, and at
    # the modules-root", and until this increment those figures were appended *after* the
    # error-class return below, so a mixed/uninspectable ERROR run disclosed none of them.
    # Appending here puts them on the ERROR, FAIL and clean paths identically. Reaching
    # here means the per-file scan completed, so the scope is the complete one, and both
    # `acct.root_files` and `coverage_counts` are necessarily set.
    notes.append(_d8_file_accounting_note(acct, coverage_counts))

    error_class = uninspectable + unattributed + coverage_violations
    if error_class:
        return GateReport("module-deps", ERROR, violations + error_class,
                          sorted(checked),
                          notes + [_d72_partition_note(violations, error_class)])

    notes += [
        f"{acct.inert} inert file(s)", f"{len(checked)} inspected file(s)",
        (f"{len(root_files)} modules-root file(s) scanned as {ROOT_IMPORTER!r} (ADR-011 D4, "
         "GATE2-R1-D4-ROOT-FILE-SCAN-2026-10-05)"),
        ("0 unattributed table identifier reference(s) (ADR-011 D3.2 state 6 is ERROR, "
         "never a benign note -- see MODULE_DEPS_TABLE_UNATTRIBUTED above when nonzero)"),
        ("coverage: only statically-resolvable Python imports and string-literal SQL inside "
         "--modules-dir are analysed; SQL reaching the database from outside this tree, "
         "ORM-reflected/driver-level dynamic SQL and non-Python/non-.sql sources are out of "
         "scope; double-quoted table identifiers (including an escaped embedded quote, and "
         "schema-qualified names mixing quoted and unquoted parts) are extracted and "
         "attributed as of GATE2-R1-D1A-QUOTED-LEXER-2026-10-05; the D6.1 broad trigger-verb "
         "set and the corrected D6.3 I-1 zero-table-statement backstop are wired in as of "
         "GATE2-R1-D6-TRIGGER-I1-2026-10-05, but CTE-local name collection (D3.2 state 3) and "
         "the rest of the SQL lexer rework remain unimplemented (ADR-011 D6); a modules-root "
         f"file (importer {ROOT_IMPORTER!r}) owns no table, so any reference to a "
         "module-owned table from such a file is a permanent FAIL CROSS_DOMAIN_SQL_IMPORT, "
         "never an ERROR -- ADR-011 D4's disclosed consequence, not a regression; the "
         "string-literal SQL analysed excludes docstring positions as of "
         "GATE2-R1-F10-D64-DOCSTRING-EXCLUSION-2026-10-05 (ADR-011 D6.4 -- see the "
         "docstring-exclusion note below for the count and its residual), and covers "
         "bytes literals as well as str as of GATE2-R1-F11-D62-BYTES-SQL-2026-10-05 "
         "(ADR-011 D6.2 -- see the bytes-literal note below for the counts and its "
         "residual); how much of that text the SQL statement trigger actually fired on "
         "is disclosed as of GATE2-R1-F12-D8-SQL-TRIGGER-COUNTER-2026-10-05 (ADR-011 D8 "
         "-- see the SQL-trigger inspection note below), so a clean verdict over a tree "
         "with no recognised SQL statement no longer reads as one over inspected SQL, "
         "and how many table-position identifiers that scan attributed -- split by "
         "ADR-011 D3.2 state, with the CTE-local state disclosed as a structurally "
         "unreachable zero -- is disclosed as of "
         "GATE2-R1-F12-D8-TABLE-STATE-COUNTERS-2026-10-05 (see the table-reference "
         "attribution note below); which of those recognised subjects carried no table "
         "position at all and are clean under ADR-011 D6.3, as against the ones refused "
         "as unresolvable, is disclosed as of "
         "GATE2-R1-F12-D8-ZERO-TABLE-COUNTER-2026-10-05 (see the zero-table note below, "
         "whose figures count individually segmented SQL statements as of "
         "GATE2-R1-F12-D8-STATEMENT-SUBJECTS-2026-10-06, cut at lexically certain "
         "top-level semicolon boundaries, with that note's LIMIT disclosing when the cut "
         "is declined back to one coarse text subject); the import half of this gate is "
         "disclosed on the same "
         "terms as of GATE2-R1-F12-D8-IMPORT-EDGE-COUNTERS-2026-10-05 -- how many "
         "cross-module Python import edges resolved to a declared module and how many of "
         "those the dependency decision approved (ADR-011 D8, see the import-edge note "
         "below), so a clean verdict over a tree with no cross-module import no longer "
         "reads as one over approved edges"),
        ("input contract fixed by ADR-011 (D1/D2 manifest schema; D3 identifier-attribution "
         "semantics wired into this scan by GATE2-R1-D1A-SCANNER-WIRING-2026-10-05, extended "
         "to quoted identifiers by GATE2-R1-D1A-QUOTED-LEXER-2026-10-05; D6.1 trigger-verb "
         "widening and the D6.3 I-1 backstop wired in by GATE2-R1-D6-TRIGGER-I1-2026-10-05; "
         "D4 _root modules-root-file scanning wired in by "
         "GATE2-R1-D4-ROOT-FILE-SCAN-2026-10-05; D5 top-level coverage reconciliation wired "
         "in by GATE2-R1-D5-NAMESPACE-COVERAGE-2026-10-05, see the coverage reconciliation "
         "note(s) above); D6's CTE-local name collection (state 3) remains unimplemented"),
    ]
    vacuous = None if substantive_any else (
        "only empty scaffolds were found; an empty scan is not evidence of compliance"
    )
    return _finish("module-deps", violations, checked, vacuous, notes)


# --- CLI -----------------------------------------------------------------------


def _rls_from_cli(args: argparse.Namespace) -> GateReport:
    if not args.runtime_role:
        return GateReport("rls", ERROR, [Violation("RLS_GATE_INPUT_INVALID", "-",
                                                   "--runtime-role is required")])
    dsn = os.environ.get(DSN_ENV)
    if not dsn:
        return GateReport("rls", ERROR, [Violation("RLS_GATE_INPUT_INVALID", "-",
                                                   f"{DSN_ENV} is not set")])
    try:
        import psycopg
    except ImportError:
        return GateReport("rls", ERROR, [Violation("RLS_GATE_INPUT_INVALID", "-",
                                                   "psycopg unavailable; use backend/.venv")])
    try:  # the manifest is always the fixed committed path (ADR-010 D3.2)
        with psycopg.connect(dsn, connect_timeout=10, autocommit=True) as conn:
            return run_rls_gate(conn, args.runtime_role, args.schema or None,
                                args.require_table)
    except psycopg.Error as exc:
        # The class name only: the message may echo connection parameters.
        return GateReport("rls", ERROR, [Violation("RLS_GATE_INPUT_INVALID", "-",
                                                   f"database error ({type(exc).__name__})")])


INTERNAL_ERROR_CODE = "MODULE_DEPS_GATE_INTERNAL_ERROR"
_FUNNEL_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _emit_internal_error(gate: str, as_json: bool, exc: BaseException) -> int:
    """ADR-011 D7.3's minimal last-resort emission for `main`'s outermost funnel.

    Deliberately does **not** construct a `GateReport` or call `render()` /
    `to_json()`. The funnel's whole purpose is to cover an unexpected throw
    *including one raised inside report emission*, so re-entering the report
    builder here would reproduce R1-F07's "non-zero exit, empty stdout" one layer
    up (D7.3's own wording). Both surfaces are therefore assembled from string
    literals: the text line mirrors `GateReport.render`'s shape by hand, and the
    `--json` branch is a hand-built object with `GateReport.to_json`'s key set in
    the same sorted order, so an existing JSON consumer still parses it.

    Only two tokens vary, and both are sanitised to `[A-Za-z0-9_.-]` so neither
    can break JSON quoting or inject a line: the gate name (as `main` recorded it
    -- the literal `module-deps` if the throw preceded argument parsing) and the
    exception's **class name**. The exception's message is never emitted: an
    arbitrary unexpected error may carry a DSN or other connection parameter,
    which `_rls_from_cli` already refuses to disclose for the same reason.

    `MODULE_DEPS_GATE_INTERNAL_ERROR` is D7's single named code for this funnel
    and is emitted for whichever gate was running; per-gate internal-error codes
    would be a new entry in each other gate's own taxonomy (ADR-009/ADR-010), not
    something to invent here. Always exit 2 (`EXIT_CODES[ERROR]`), never PASS.
    """
    label = _FUNNEL_TOKEN_RE.sub("", gate) or "module-deps"
    kind = _FUNNEL_TOKEN_RE.sub("", type(exc).__name__) or "Exception"
    detail = f"unexpected {kind} escaped the gate; no gate verdict was reached"
    if as_json:
        print(
            "{\n"
            '  "checked": [],\n'
            f'  "gate": "{label}",\n'
            '  "inventory": [],\n'
            '  "notes": [],\n'
            f'  "status": "{ERROR}",\n'
            '  "violations": [\n'
            "    {\n"
            f'      "code": "{INTERNAL_ERROR_CODE}",\n'
            f'      "detail": "{detail}",\n'
            '      "subject": "-"\n'
            "    }\n"
            "  ]\n"
            "}"
        )
    else:
        print(f"[{label}] {ERROR} — checked 0 subject(s)")
        print(f"  {INTERNAL_ERROR_CODE}: - — {detail}")
    return EXIT_CODES[ERROR]


def main(argv: Sequence[str] | None = None) -> int:
    """ADR-011 D7.3's outermost funnel: every path out of here either emits a
    report and returns its exit code, or emits the minimal internal-error line
    and returns 2. No path returns non-zero with nothing on stdout, and no path
    returns 0 without a report -- that was R1-F07's exact shape.

    Everything the CLI does lives inside the `try`, including argument parsing
    and the `print`, so a throw raised *while emitting* the report is funnelled
    too; that is the case `_emit_internal_error` must not re-enter the builder
    for. `gate_label`/`as_json` are seeded before the `try` and overwritten the
    moment argparse yields the real values, so the funnel never has to re-parse
    `argv` itself to pick its surface.
    """
    gate_label, as_json = "module-deps", False
    try:
        parser = argparse.ArgumentParser(
            description=__doc__.split("\n\n")[0] if __doc__ else None)
        parser.add_argument("--gate", required=True, choices=IMPLEMENTED_GATES + DEFERRED_GATES)
        parser.add_argument("--json", action="store_true", help="emit the report as JSON")
        parser.add_argument("--runtime-role", help="rls: production-equivalent runtime role")
        parser.add_argument("--schema", action="append", default=[], help="rls: limit scan")
        parser.add_argument("--require-table", action="append", default=[],
                            help="rls: schema.table that must exist as a tenant table")
        parser.add_argument("--openapi-dir", type=Path, default=DEFAULT_OPENAPI_DIR)
        parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
        parser.add_argument("--modules-dir", type=Path, default=DEFAULT_MODULES_DIR,
                            help="module-deps: root package directory to scan")
        parser.add_argument("--module-manifest", type=Path, default=DEFAULT_MODULE_MANIFEST,
                            help="module-deps: ownership manifest")
        parser.add_argument("--event-source-dir", type=Path, default=DEFAULT_EVENT_SOURCE_DIR,
                            help="event-contract: Python source tree")
        parser.add_argument("--event-registry", type=Path, default=DEFAULT_EVENT_REGISTRY,
                            help="event-contract: current JSON Schema registry")
        parser.add_argument("--event-baseline", type=Path, default=DEFAULT_EVENT_BASELINE,
                            help="event-contract: pinned previous registry")
        parser.add_argument("--event-approval-root", type=Path, default=REPO_ROOT,
                            help="event-contract: root containing OWNER_APPROVALS.md")
        args = parser.parse_args(argv)
        gate_label, as_json = args.gate, bool(args.json)

        if args.gate == "rls":
            report = _rls_from_cli(args)
        elif args.gate == "permission":
            report = run_permission_gate(args.openapi_dir, args.registry)
        elif args.gate == "module-deps":
            report = run_module_deps_gate(args.modules_dir, args.module_manifest)
        elif args.gate == "event-contract":
            report = run_event_contract_gate(args.event_source_dir, args.event_registry,
                                             args.event_baseline, args.event_approval_root)
        else:
            report = GateReport(args.gate, ERROR, [Violation(
                "GATE_NOT_IMPLEMENTED", args.gate,
                "not implemented in the GOV-01-R04 critical slice; never reported as PASS",
            )])
        print(report.to_json() if args.json else report.render())
        return report.exit_code
    except Exception as exc:  # noqa: BLE001 -- D7.3's deliberate outermost funnel.
        # `Exception`, never `BaseException`: D7.3 forbids catching `SystemExit`
        # (argparse's own `--help`/usage exit path, and `sys.exit(main())` below)
        # or `KeyboardInterrupt`.
        return _emit_internal_error(gate_label, as_json, exc)


if __name__ == "__main__":
    sys.exit(main())

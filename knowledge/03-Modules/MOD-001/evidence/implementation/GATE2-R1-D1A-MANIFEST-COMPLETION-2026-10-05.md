---
doc: GATE2-R1-D1A-MANIFEST-COMPLETION
status: BOUNDED MANIFEST-COMPLETION STEP — NOT a review round, NOT a
  remediation round, NOT a certification step. D1a is still not complete
  after this step (see §4 — D3 identifier-attribution semantics actually
  used during SQL scanning remain entirely unimplemented).
date: 2026-10-05
module: MOD-001 (GOV-01-R04, TSD §24.1 gate 2 — module dependency / cross-domain
  SQL lint)
scope: Exactly three files touched — `tools/validate_architecture_gates.py`,
  `tools/tests/test_validate_architecture_gates.py`, and this evidence note.
  No other source, manifest, workflow, or knowledge file touched. No git
  commit/push performed.
---

# Gate-2 round-1 D1a manifest completion — three deferred ADR-011 invariants

## 1. Starting state

`GATE2-R1-D1A-STABILIZATION-2026-10-05.md` left `parse_module_manifest` at
**106 passed / 0 failed**, having implemented ADR-011 D1/D2's schema-level
checks only, and explicitly deferred three D3 manifest-level invariants (its
§4) as "in-scope-adjacent but not implemented":

1. `owned_schemas` reserved-value check (D3.4, mirroring the existing
   `owned_table_prefixes` reserved check).
2. `default_schema` disjoint from any module's `owned_schemas` (D3.3(3)/b2(i)).
3. `external_table_references` D3.5 cross-check — an entry may not resolve to
   any module's `owned_table_prefixes` or `owned_schemas`.

This session implemented exactly those three, and nothing else, inside
`parse_module_manifest` (plus one new private helper it calls). No change to
`_resolve_owner`, `_scan_sql_text`, `_is_sql_ish`, `_dangling_keywords`, or any
other identifier-attribution (D3/I-2, used during SQL scanning) or scanning
(D4/D5/I-3) code path — those remain the separate, not-yet-implemented slice
the stabilization report's §5 already disclosed, and this report's §4 restates
explicitly rather than silently narrowing.

## 2. Invariants implemented

**(a) Reserved `owned_schemas` values (ADR-011 D3.4).** The ADR's own
wording — *"pg_, pg_catalog, pg_temp and information_schema are rejected at
parse time as owned_table_prefixes **or owned_schemas** values"* — means the
same four-value `_RESERVED_MANIFEST_VALUES` set (not the narrower,
three-value `_RESERVED_SCHEMA_NAMES` constant left unwired by the prior
session) governs both fields. `pg_` satisfies `owned_schemas`'s generic
identifier regex (there is no trailing-underscore floor for schemas, unlike
prefixes) and would otherwise silently pass. Checked in the existing
per-module `owned_schemas` loop, after the identifier-format check and before
the cross-module duplicate-schema check.

**(b) `owned_schemas` disjoint from `default_schema` (ADR-011 D3.3(3)/b2(i)).**
A module declaring the default schema as one of its own `owned_schemas`
entries would, once D3's resolution semantics are eventually wired in,
capture every bare table resolved under that schema as state-1 clean — the
qualified-lead decision's b2(i) correction exists specifically to close this
before it opens. Checked in the same loop, immediately after the reserved-
value check, comparing each `owned_schemas` entry against the module manifest's
own (possibly defaulted) `default_schema` value.

**(c) `external_table_references` never resolves to any declared module's
owned prefix or schema — including the declaring module's own (ADR-011
D3.5/b1).** This is the cross-check the stabilization report deferred because
"the ownership cross-check requires the same attribution machinery D3/I-2
owns." Implemented at the manifest-parse-time level only (no SQL scanning
involved), as a second pass after every module's `owned_table_prefixes` and
`owned_schemas` are known — necessary because a reference may name a module
declared later in manifest key order, or the declaring module's own entry.

A new private helper, `_external_ref_conflict(ref, default_schema,
seen_schemas, all_prefixes)`, resolves one reference the same way ADR-011
D3.3 rule 2 resolves a real identifier: a 2-part `schema.table` reference is
checked against `owned_schemas` unless its schema part equals
`default_schema`, in which case the schema is stripped and the remaining
table part is checked against `owned_table_prefixes` instead — exactly like
a real identifier would resolve. Without that strip-and-fall-through step, a
module could bypass the check entirely by wrapping an owned prefix in the
default schema (e.g. `public.mem_roster` instead of `mem_roster`); this is
exercised directly by
`test_d35_external_table_reference_wrapped_in_default_schema_is_rejected`.
A 1-part reference is checked directly against `owned_table_prefixes`. The
helper returns `(conflicting_owner, descriptor)` or `None`; `parse_module_
manifest` raises `GateInputError` naming the declaring module, the offending
entry, the resolved owner, and which field it resolved against.

All three checks run at parse time inside `parse_module_manifest`, raise the
same `GateInputError` type every other manifest-schema violation in this
function raises, and every message follows the file's existing convention:
it names the offending value, the module it came from, and (via an inline
`ADR-011 D3.x` citation) the invariant violated.

## 3. Tests added

11 new focused tests added to `tools/tests/test_validate_architecture_gates.py`,
calling `parse_module_manifest` directly — same style as the stabilization
report's own 16 D1/D2 tests, each with a positive and/or negative case:

- `test_d34_reserved_schema_value_pg_catalog_is_rejected` (negative)
- `test_d34_reserved_schema_value_pg_prefix_itself_is_rejected` (negative —
  the case ADR-011 calls out by name, since `pg_` has no floor to catch it
  incidentally the way it does for prefixes)
- `test_d2_owned_schemas_non_reserved_value_passes` (positive)
- `test_d33_owned_schemas_entry_equal_to_default_schema_is_rejected`
  (negative, implicit default `"public"`)
- `test_d33_owned_schemas_entry_equal_to_custom_default_schema_is_rejected`
  (negative, explicit custom `default_schema`)
- `test_d33_owned_schemas_disjoint_from_default_schema_passes` (positive)
- `test_d35_external_table_reference_resolving_to_own_prefix_is_rejected`
  (negative — the declaring module's own prefix, per the task's explicit
  "including the current module's own")
- `test_d35_external_table_reference_resolving_to_other_modules_prefix_is_rejected`
  (negative, cross-module)
- `test_d35_external_table_reference_resolving_to_owned_schema_is_rejected`
  (negative, schema-qualified)
- `test_d35_external_table_reference_wrapped_in_default_schema_is_rejected`
  (negative — the default-schema bypass shape named in §2(c) above)
- `test_d35_external_table_reference_not_resolving_to_any_owner_passes`
  (positive)

**Regression preservation, explicitly checked, not assumed:** both pre-existing
tests this task's instructions named by name were re-run and still pass
unchanged —
`test_d2_duplicate_overlap_detection_unchanged_same_module_nested_accepted`
(same-module nested-prefix ACCEPT) and
`test_d2_duplicate_overlap_detection_unchanged_cross_module_overlap_rejected`
(cross-module prefix overlap REJECT). Neither new check touches the
`all_prefixes` overlap-detection loop or its inputs.

## 4. Verification (executed)

```
$ python -m py_compile tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
  (no output — compiled clean)
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q
117 passed in 1.78s
$ backend/.venv/bin/python tools/tests/test_validate_architecture_gates.py   # the file's own
                                                                              # standalone, non-pytest runner
PASS — all 117 tests passed.
$ backend/.venv/bin/python -m ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
All checks passed!
$ backend/.venv/bin/python -m mypy tools/validate_architecture_gates.py
Success: no issues found in 1 source file
```

**Result: 117 passed / 0 failed (106 pre-existing from the stabilization
step + 11 new), both collection paths (pytest and the file's own manual
runner) agree, ruff and mypy clean, zero regressions.**

## 5. What was NOT done (explicit, per the task's "no false completion"
instruction)

- **D1a is still not complete.** Only three additional D3 manifest-level
  invariants were implemented. The following remain entirely unimplemented,
  exactly as the stabilization report's own §4/§5 already disclosed and
  unchanged by this step:
  - **D3's six-state identifier-attribution table** as actually used during
    SQL scanning. `_resolve_owner` still implements the pre-ADR-011
    "unowned ⇒ disclosed, not flagged" behavior, not D3.2's six states; it
    was not read, let alone edited, by this session beyond confirming (by
    grep) that it is untouched.
  - **D4's `_root` scanning behavior** beyond the manifest-level name
    reservation already in place before this session.
  - **D5 (coverage reconciliation)** and **D6 (the SQL lexer rework)** —
    the `_TRIGGER_VERBS`/`_TABLE_POSITION_KEYWORDS`/`_BARE_VERB_FORMS`/
    `ATTR_*` scaffolding constants remain exactly as found: defined, present,
    and unreferenced anywhere else in the file.
  - **No I-1 check** (zero-table-statement backstop).
- **No SQL lexer touched.** `_is_sql_ish`/`_dangling_keywords`/
  `_TABLE_IDENT_RE` are untouched.
- **No root `ruff.toml`.** The task's out-of-scope list named this
  explicitly; not authored.
- **No CI wiring.** No `.github/workflows/` change of any kind.
- **No real ownership manifest.** No `contracts/modules/ownership.json` was
  authored, implied, or made authorable — ADR-011's own scope limit ("binds
  NO real scaffold and NO domain logic") is unaffected by this step.
- **No domain mappings.**
- **No independent review.** This is implementation work product only — a
  fresh independent review is the explicit next action before any
  promotion/certification claim.
- **No scenario PASS claim.** Nothing in `SCENARIOS.md`, `SCN-070`, or
  `DOM-002` was touched or claimed.
- **No git commit, push, or any git write operation.** `git status`
  confirms only the two in-scope tool files are untracked (both were already
  untracked before this session, per the stabilization report — there is no
  prior committed version of either); no other file in the working tree was
  touched by this session.

## 6. Final counts (for the orchestrator's report)

| Check | Result |
|---|---|
| Starting state (post-stabilization) | 106 passed / 0 failed |
| Post-manifest-completion (final) | **117 passed / 0 failed** (106 pre-existing + 11 new) |
| `ruff check` (both files) | All checks passed |
| `mypy` (`validate_architecture_gates.py`) | Success: no issues found |
| Files touched | `tools/validate_architecture_gates.py`, `tools/tests/test_validate_architecture_gates.py`, plus this evidence note |
| Git commit/push | None performed |
| D1a overall status | **Still not complete** — D3 (attribution/scanning), D4 (`_root` scanning), D5 (coverage), D6 (SQL lexer), I-1, I-2 remain unimplemented |

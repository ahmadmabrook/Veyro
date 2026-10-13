---
doc: GATE2-MODULE-DEPS-CODE-REVIEW-ROUND1
module: MOD-001
work_unit: GOV-01-R04 — TSD §24.1 gate 2 (module-dependency / cross-domain SQL lint)
scenarios_in_scope: SCN-MOD001-006, SCN-MOD001-007, SCN-MOD001-095, SCN-MOD001-096
round: 1 (first completed independent code review for THIS semantic unit)
date: 2026-10-05
reviewer_role: veyro-code-reviewer (fresh independent context, Opus tier)
reviewer_model: claude-opus-5[1m] — Opus 5 (1M context)
subagent_id: a4e01615878caa08c
verdict: BLOCKED
p0: 1
p1: 7
p2: 6
p3: 7
review_type: CODE ASSURANCE ONLY — no scenario promotion, no sign-off, no remediation
claim: REVIEW_IN_FLIGHT.md current_claim (prewritten, honored — not overwritten by this review)
---

# Gate-2 (module-deps) Independent Code Review — Round 1

## Orchestrator framing (top-level coordination record)

This document is the durable capture of a **single** fresh independent
`veyro-code-reviewer`/Opus dispatch. The top-level session coordinated only:
it verified the snapshot hashes, verified the governance paths, honored the
prewritten `REVIEW_IN_FLIGHT.md` claim, dispatched exactly one reviewer, and
persisted the reviewer's verdict and report body below. The top-level session
made **no code edits, no commits, no pushes, and no remediation**, and did not
itself perform the review.

**Round accounting.** This is round **1** for this semantic unit (0 completed
before this dispatch). The SCN-MOD001-070 counter (5) and the DOM-002 counter
(4) are unrelated historical counters; they were not reset, reused, or touched.

**Scope boundaries honored.** No SCN-MOD001-070, no DOM-002, no RLS gate, and
no permission-lint / "permission A2" review. Scenario-catalog review remains a
separate role (`veyro-scenario-reviewer`) and is not performed or pre-empted
here.

**Owner-reserved restrictions.** No paid services, no spend, no real member
data (synthetic fixtures only), no deploy or production action, no material
product/architecture/scope change. The reviewer confirmed all of these.

**Snapshot integrity (verified by the top-level session before dispatch, and
independently by the reviewer at start and end of review):**

| File | Expected SHA-256 | Observed |
|---|---|---|
| `tools/validate_architecture_gates.py` | `f50c3c6a43ac984cd9381731b90706d28f30ff7b42a5b6b28d28ffcf87386046` | match |
| `tools/tests/test_validate_architecture_gates.py` | `26e528e8c099e90d344db5085fac8d2974c126b46220006c05a77914d537833b` | match |

No snapshot mismatch. Hashes still matched after all probing, proving nothing
drifted mid-review. Both files are untracked WIP, consistent with the
governing decision record.

**Changed-file hashes.** No files were changed by this review. The two review
targets retain the snapshot hashes above. The reviewer's `git status
--porcelain` output was identical to the pre-existing working-tree state
(34 tracked modifications plus untracked WIP, 352 entries); a grep of the
full porcelain output for `validate_architecture_gates|/tmp/gate2` returned
only the two pre-existing untracked review targets:

```
?? tools/validate_architecture_gates.py
?? tools/tests/test_validate_architecture_gates.py
```

All reviewer-authored probe artifacts live under `/tmp/gate2_review_r1/`,
outside the repository.

---

## Reviewer report (verbatim)

**Work unit:** MOD-001 `GOV-01-R04`, TSD §24.1 **gate 2** (module dependency / SQL lint), scenarios SCN-MOD001-006 / -007 / -095 / -096
**Reviewer role:** fresh independent `veyro-code-reviewer`, round 1 for this semantic unit
**Date:** 2026-10-05
**Subject files:** `tools/validate_architecture_gates.py`, `tools/tests/test_validate_architecture_gates.py` (both untracked WIP, consistent with the decision record)

### 1. Verdict

**BLOCKED**

| Severity | Count |
|---|---|
| P0 | 1 |
| P1 | 7 |
| P2 | 6 |
| P3 | 7 |

The Verdict C three-case rule is **correctly and completely implemented** (probed; §6 below), the four §6.3 directed pairs are enforced **independently and correctly in both directions**, and the fixture-scoped evidence set is honestly labeled and reproduces. The block is not about Verdict C. It is about the gate's **table-attribution and scan-coverage model**, where I found one path on which a cross-domain raw SQL reference — the literal subject of SCN-MOD001-007 — passes with exit 0 after a one-token edit, plus six further silent-pass paths. Three of the P1s (R1-F03, R1-F04, R1-F07) are reachable in the real tree today, not only in crafted fixtures.

### 2. Snapshot verification

| | Start of review | End of review | Match |
|---|---|---|---|
| `tools/validate_architecture_gates.py` | `f50c3c6a43ac984cd9381731b90706d28f30ff7b42a5b6b28d28ffcf87386046` | `f50c3c6a43ac984cd9381731b90706d28f30ff7b42a5b6b28d28ffcf87386046` | yes |
| `tools/tests/test_validate_architecture_gates.py` | `26e528e8c099e90d344db5085fac8d2974c126b46220006c05a77914d537833b` | `26e528e8c099e90d344db5085fac8d2974c126b46220006c05a77914d537833b` | yes |

Both expected hashes matched on first run and again after all probing. Nothing drifted mid-review.

### 3. Scope statement

**Reviewed:** the gate-2 parse path (`parse_module_manifest`, `load_module_manifest`), module discovery (`_modules_root_package`, `_discover_modules`, `_walk_module`, `_categorize`), import-edge detection (`_file_package_info`, `_resolve_relative`, `_import_targets`, `_import_violation`, `BIDIRECTIONAL_PAIRS`), raw SQL / dynamic-construct detection (`_is_sql_ish`, `_dangling_keywords`, `_resolve_owner`, `_scan_sql_text`, `_is_dynamic_import_call`, `_uninspectable_for_node`), the vacuity rule (`_is_substantive`), the orchestrator `run_module_deps_gate`, the output/exit contract (`GateReport`, `_finish`, `EXIT_CODES`, `main`), the gate-2 tests, and the three implementation records plus the governing decision record.

**Deliberately excluded (per dispatch bounds):** SCN-MOD001-070, DOM-002, the RLS gate (`--gate rls`, ADR-010 paths), the permission gate / "permission A2" review. I read shared helpers (`_load_json`, `_finish`, `GateReport`) only because gate 2 calls them, and report on them only where gate 2's behavior depends on them.

**Out-of-scope observations (one line each, not findings):** the `rls` CLI path returns only `type(exc).__name__` for psycopg errors (`:1848-1851`) — deliberate, looks sound, not reviewed further. `DEFERRED_GATES` correctly refuse with exit 2 rather than PASS (`:1876-1880`).

### 4. Findings

All findings are **NEW**. `knowledge/03-Modules/MOD-001/evidence/code-review/` contains no prior gate-2 review (the directory holds BUG-048 slice-5, CAP-008, DOM-002 rounds 1-4, SCN-MOD001-009, and GOV-01-R02 scaffolds only), so there is nothing RECURRING to compare against.

---

#### R1-F01 · **P0** · Cross-domain raw SQL is defeatable by identifier form: `public.`-qualification or upper-casing yields a silent PASS

**Evidence:** `tools/validate_architecture_gates.py:1594-1608`

```python
def _resolve_owner(identifier: str, modules: Mapping[str, ModuleEntry]) -> str | None:
    if "." in identifier:
        schema = identifier.split(".", 1)[0]
        for mod in modules.values():
            if schema in mod.owned_schemas:
                return mod.name
        return None          # <-- qualified identifiers NEVER consult owned_table_prefixes
    best: tuple[int, str] | None = None
    for mod in modules.values():
        for prefix in mod.owned_table_prefixes:
            if identifier.startswith(prefix) and (best is None or len(prefix) > best[0]):
```

Two independent defects in one function. (a) A schema-qualified identifier whose schema is unowned returns `None` **without ever testing the bare table name against `owned_table_prefixes`** — so `public.bil_invoices` is "unowned" while `bil_invoices` is a violation. In a single-schema deployment — which is exactly the deployment shape `owned_table_prefixes` exists to serve — every qualified reference is `public.<prefix>_table` and is never checked. (b) `startswith` is case-sensitive while `_TABLE_IDENT_RE` (`:1369-1371`) captures case-insensitively, so `BIL_INVOICES` is captured verbatim and resolves to `None`. PostgreSQL folds unquoted identifiers to lower case, so both forms address the same table.

**Reproducer:** `/tmp/gate2_review_r1/p10_schema.py` (fixture manifest: module `a` = COM-01 owns `a_`/schema `sa`; module `bb` = COM-03 owns `bil_`/schema `sb`; `a/q.py` holds one string literal).

```
bare bil_invoices (control)      exit=1 viol=True | CROSS_DOMAIN_SQL_IMPORT: a -> bb — a/q.py:1: table 'bil_invoices' owned by 'bb'
public.bil_invoices              exit=0 viol=False | note: 1 unowned table identifier reference(s) (not flagged): public.bil_invoices
uppercase BIL_INVOICES           exit=0 viol=False | note: 1 unowned table identifier reference(s) (not flagged): BIL_INVOICES
db.schema.table 3-part           exit=0 viol=False | note: 1 unowned table identifier reference(s) (not flagged): db.sb
schema sb.bil_invoices           exit=1 viol=True | CROSS_DOMAIN_SQL_IMPORT: a -> bb — a/q.py:1: table 'sb.bil_invoices' owned by 'bb'
```

A three-part name (`db.sb.bil_invoices`) is additionally mis-captured as `db.sb` by `_TABLE_IDENT_RE`'s two-segment ceiling, losing the table name entirely.

**Why it matters against the governing decision:** TSD §24.1 (`TSD_MIRROR.md:11602-11604`) makes "cross-domain raw SQL/ORM imports fail CI" the gate's headline invariant, and the decision record's required evidence item 2 (Verdict A, "How gate 2 is still ACCEPTED") is a `CROSS_DOMAIN_SQL_IMPORT` proof. SCN-MOD001-007's own acceptance text is a cross-domain raw-table reference. The gate returns PASS exit 0 for that violation after prepending `public.` or shifting case — no manifest cooperation, no exotic construct, no disclosure beyond a generic "not flagged" note that reads as benign. This is "defeatable on a path it must catch". The rationale for not flagging unowned identifiers (CTEs, aliases, catalog tables) is sound, but it cannot be the reason a *qualified owned-prefix* table escapes attribution.

---

#### R1-F02 · **P1** · DDL, `MERGE`, `COPY`, `LOCK TABLE` and `GRANT` on another module's table silently PASS

**Evidence:** `tools/validate_architecture_gates.py:1373`

```python
_SQL_DML_RE = re.compile(r"(?i)\b(?:SELECT|INSERT|UPDATE|DELETE|TRUNCATE)\b")
```

`_is_sql_ish` (`:1585-1586`) requires one of those five verbs, so any statement whose verb is `CREATE`/`ALTER`/`DROP`/`MERGE`/`COPY`/`LOCK`/`GRANT` is not SQL-ish and is never scanned at all.

**Reproducer:** `/tmp/gate2_review_r1/p5_sql.py`, each case a single string literal in `membership/q.py` referencing `billing`'s owned table:

```
plain SELECT (control)         exit=1 FAIL  ['CROSS_DOMAIN_SQL_IMPORT']
MERGE INTO                     exit=0 PASS  []
COPY                           exit=0 PASS  []
ALTER TABLE (DDL)              exit=0 PASS  []
CREATE TABLE (DDL)             exit=0 PASS  []
DROP TABLE (DDL)               exit=0 PASS  []
LOCK TABLE                     exit=0 PASS  []
GRANT                          exit=0 PASS  []
```

**Why it matters:** `'DROP TABLE bil_invoices'` in module `membership` is as complete a cross-domain reference as a `SELECT`, and the gate reports PASS. Worse, the report's own coverage note states that "string-literal SQL inside --modules-dir **are** analysed", which a reader will reasonably take to include these literals. The docstring's "What this gate does not prove" paragraph (`:249-255`) lists out-of-tree SQL, ORM-reflected SQL and non-Python sources — it does not disclose that DDL/`MERGE`/`COPY` are unexamined. Either the detector covers them or the limitation must be on the face of the report; neither is true today.

---

#### R1-F03 · **P1** · Files directly under `--modules-dir` are never inspected, and the omission is not disclosed

**Evidence:** `tools/validate_architecture_gates.py:1748-1761`

```python
scan_dirs = [(name, modules_dir / name) for name in discovered]
shared_dir = modules_dir / SHARED_PACKAGE
...
for importer, mod_dir in scan_dirs:
    for path in _walk_module(mod_dir):
```

`_walk_module` is only ever called on a discovered module directory or `_shared`. Any file sitting at the `--modules-dir` root — including `__init__.py` and `conftest.py` — is never opened, never categorised, and never counted.

**Reproducer:** `/tmp/gate2_review_r1/p4_coverage.py` cases A and B. The planted file contains *both* a cross-domain internal import and cross-domain SQL:

```
=== P4a violation in <modules-dir>/conftest.py :: exit=0
  note: 2 scanned module(s)
  note: 4 inspected file(s)
=== P4b violation in <modules-dir>/__init__.py :: exit=0
  note: 2 scanned module(s)
  note: 4 inspected file(s)
```

**Why it matters:** `backend/app/modules/conftest.py` **exists in the real tree today** (`git status --porcelain` → `?? backend/app/modules/conftest.py`), so this is not hypothetical. The tool applies closed-set discipline to file *extensions* — an unrecognised suffix is a hard `GateInputError` (`:1537-1546`) — but silently skips an entire `.py` file because of its location. At minimum the report must disclose "N file(s) at the modules-dir root were not inspected"; as written, a reader cannot tell the difference between "clean" and "unexamined".

---

#### R1-F04 · **P1** · A directory without `__init__.py` is never scanned, yet is an importable Python 3 namespace package

**Evidence:** `tools/validate_architecture_gates.py:1501-1512`

```python
if entry.is_dir() and (entry / "__init__.py").is_file():
    names.append(entry.name)
```

**Reproducer:** `/tmp/gate2_review_r1/p4_coverage.py` case F — `rogue/x.py` contains a cross-domain internal import and cross-domain SQL, and `rogue/` has no `__init__.py`:

```
=== P4f module dir without __init__.py (undiscovered) :: exit=0
  note: 2 scanned module(s)
  note: 4 inspected file(s)
```

**Why it matters:** since PEP 420, `app.modules.rogue.x` is fully importable without `__init__.py`, so the evader pays no functional price. Deleting one empty file removes a whole package from the gate's view, with no note, no count and no ERROR. The inbound direction does fail closed (another module importing `app.modules.rogue.x` raises `MODULE_DEPS_GATE_INPUT_INVALID`, probed under `p6` "import of undeclared module"), but the rogue package's **own** outbound violations are invisible. `GOV-01-R04` requires that no gate be bypassable at the CI-configuration layer; this is bypassable one layer below that, at source-tree layout, which the discovery contract documents but does not mitigate.

---

#### R1-F05 · **P1** · The dynamic-import fail-closed set is bypassable by four ordinary idioms

**Evidence:** `tools/validate_architecture_gates.py:1656-1665`

```python
if isinstance(f, ast.Name):
    return f.id == "__import__"
if isinstance(f, ast.Attribute):
    return (f.attr in ("import_module", "__import__")
            and isinstance(f.value, ast.Name) and f.value.id == "importlib")
```

Detection is bound to the literal name `importlib` as the receiver, or the bare name `__import__`.

**Reproducer:** `/tmp/gate2_review_r1/p6_imports.py`

```
importlib.import_module                  exit=2 ERROR  ['MODULE_DEPS_SOURCE_UNINSPECTABLE']
__import__ builtin                       exit=2 ERROR  ['MODULE_DEPS_SOURCE_UNINSPECTABLE']
from importlib import import_module      exit=0 PASS   []
aliased import_module                    exit=0 PASS   []
builtins.__import__                      exit=0 PASS   []
getattr(importlib,...)                   exit=0 PASS   []
exec of import stmt                      exit=0 PASS   []
```

**Why it matters:** `_uninspectable_for_node`'s own docstring (`:1668-1670`) calls this "The closed set of statically-unprovable constructs ... never extended with an 'etc.' case". The most idiomatic form in real code — `from importlib import import_module` — bypasses it and the gate reports PASS exit 0 while the file does exactly what the construct was meant to make inadmissible. `exec("from app.modules.billing.internals import s")` likewise passes. The intended fail-closed property is only as strong as a name match.

*(Credit where due: the statically-resolvable import surface is otherwise solid. `import`/`import as`/relative level-2/`TYPE_CHECKING`-guarded/`try`-guarded/function-local/star imports are all caught, `_shared` re-export laundering is caught at the shim, and the `apiv2`-vs-`api` string-prefix trap is correctly rejected because `_import_violation:1705` matches on `iface + "."` rather than a bare `startswith`.)*

---

#### R1-F06 · **P1** · SQL assembled by `.join()` or by an f-string with the verb interpolated is neither scanned nor flagged uninspectable

**Evidence:** `tools/validate_architecture_gates.py:1676-1689`. The `JoinedStr` branch requires the *literal* parts to be SQL-ish; the `BinOp` branch covers only `+` and `%`. Nothing covers `str.join`, a list of fragments, or a verb-interpolated f-string.

**Reproducer:** `/tmp/gate2_review_r1/p5_sql.py`

```
join() of fragments                            exit=0 PASS  []
list element then concat at runtime            exit=0 PASS  []
f-string w/ table literal, DML interpolated    exit=0 PASS  []
percent format                                 exit=2 ERROR ['MODULE_DEPS_SOURCE_UNINSPECTABLE']
.format()                                      exit=2 ERROR ['MODULE_DEPS_SOURCE_UNINSPECTABLE']
```

`" ".join(['SELECT a', 'FROM bil_invoices'])` passes because neither fragment is SQL-ish alone. `f'{op} a FROM bil_invoices'` passes because the literal part lacks a DML verb — note the table name here is a **plain literal**, fully statically visible, and still unexamined. `.format()` and `%` are caught only incidentally, via the dangling-keyword heuristic.

**Why it matters:** this is the same failure mode as R1-F05 in the SQL half: the gate's fail-closed construct is shape-bound, so the evasion is a silent PASS rather than an ERROR.

---

#### R1-F07 · **P1** · A non-UTF-8 source file crashes the gate: no report, no JSON, exit 1 instead of the contractual ERROR/2

**Evidence:** `tools/validate_architecture_gates.py:1770` and `:1774`

```python
text = path.read_text(encoding="utf-8")      # .sql
...
source = path.read_text(encoding="utf-8")    # .py
```

`UnicodeDecodeError` is not a `GateInputError` and is not caught by the handler at `:1806`. The manifest path handles this correctly (`_load_json:1270` catches `UnicodeDecodeError`); source files do not.

**Reproducer:** `/tmp/gate2_review_r1/p7_failclosed.py` and `/tmp/gate2_review_r1/p9_misc.py` case B.

```
non-UTF8 .py (latin-1 byte)      exit=1 NO-REPORT
        STDERR tail: UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 5: invalid continuation byte
valid latin-1 .py w/ cookie      exit=1 NO-REPORT
        STDERR tail: UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 32: invalid continuation byte
non-UTF8 .sql                    exit=1 NO-REPORT
        STDERR tail: UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 8: invalid continuation byte

--- B --json on non-UTF8 file: exit=1 stdout_len=0 stdout=''
```

**Why it matters:** the tool's own outcome contract (`:24-31`) assigns exit 1 to "FAIL — at least one named violation" and exit 2 to "ERROR — unusable input (unreadable/unsupported/malformed)". An unreadable file produces exit 1 with **zero** stdout, so a CI consumer reading `--json` gets an empty string and a reader sees the exit code for "a violation was found". The second case (`# -*- coding: latin-1 -*-`) is *legal Python that imports fine* — this is reachable without any adversary. Not fail-open (non-zero), hence P1 rather than P0.

---

#### R1-F08 · **P1** · Manifest module names are unvalidated; a dotted name lets one module read another declared module's internals with a PASS

**Evidence:** `tools/validate_architecture_gates.py:1409-1419` — the loop validates `domain` against `_DOMAIN_CODE_RE`, prefixes and schemas against `_MODULE_NAME_IDENT_RE`, and interfaces against `_INTERFACE_PATH_RE`, but the **key** `name` is only checked for `!= "_shared"`. Target resolution then takes the first dotted segment only (`:1788-1789`):

```python
remainder = resolved[len(modules_root) + 1:]
target = remainder.split(".", 1)[0]
```

**Reproducer:** `/tmp/gate2_review_r1/p9_misc.py` case A. Manifest declares `pos` (COM-05, `public_interfaces: ["app.modules.pos.v2"]`), `pos.v2` (COM-06, its own domain and prefixes) and `other` (COM-01). Directory `app/modules/pos.v2/` exists with `api.py` and `secret.py`. `other/u.py` contains `from app.modules.pos.v2.secret import S`:

```
--- A other -> 'pos.v2' internals, approved as pos's iface? exit=0 PASS
```

Module `other` reads module `pos.v2`'s non-interface internals and the gate approves it as `pos`'s declared public interface via the submodule rule at `:1705`. Separately, `/tmp/gate2_review_r1/p8_manifest.py` case A2 confirms a directory literally named `pos.v2` is accepted as a discovered module.

**Why it matters:** Verdict C's stated invariant is "unambiguous attribution of a table to exactly one owner", and the same reasoning governs import attribution. An input contract described as "deliberately closed and strict" (decision record, Verdict C rationale) leaves its primary key — the module name — entirely unvalidated. Exploitability today is low because the manifest is owner-blocked under Verdict A, but this becomes live the moment a manifest is authored, and `_MODULE_NAME_IDENT_RE` already exists one line away.

---

#### R1-F09 · **P2** · Uninspectable findings suppress every real violation in the same run

**Evidence:** `:1810-1811` returns ERROR with *only* the uninspectable list, discarding `violations`.

**Reproducer:** `/tmp/gate2_review_r1/p9_misc.py` case E — the tree contains a genuine cross-domain internal import *and* cross-domain SQL in `a/v.py`, plus one f-string in `a/d.py`:

```
--- E real violations + one f-string in same run exit=2 ERROR
    MODULE_DEPS_SOURCE_UNINSPECTABLE: a/d.py:2 — f-string with SQL-ish literal parts and an interpolated value
    MODULE_DEPS_SOURCE_UNINSPECTABLE: a/d.py:2 — SQL-ish text has a FROM/JOIN/INTO/UPDATE/TABLE keyword not followed by an identifier
```

Neither real violation appears. The docstring discloses the design ("never folded into a FAIL alongside other violations", `:240-242`) and the run is non-zero, so this is not a bypass. But the operational consequence is that one dynamic SQL string anywhere in the tree hides all genuine violations until removed, and it gives a module a way to make its violations invisible in the report while the exit code stays non-zero for an unrelated-looking reason. Worth a lead decision, not a silent accept.

#### R1-F10 · **P2** · English prose in a docstring produces a hard `CROSS_DOMAIN_SQL_IMPORT` FAIL

`:1801-1805` scans every `ast.Constant` string, which includes module/class/function docstrings. Reproducer (`/tmp/gate2_review_r1/p5_sql.py`): `"""Select the row from bil_invoices when syncing."""` as the sole content of `membership/q.py` →

```
docstring prose FALSE POSITIVE   exit=1 FAIL  ['CROSS_DOMAIN_SQL_IMPORT']
```

Fails closed, so not a security issue — but a false FAIL on documentation prose creates exactly the pressure to weaken the gate that this project's rules exist to resist. (Comments are safely invisible, being absent from the AST.)

#### R1-F11 · **P2** · Bytes-literal SQL is not scanned

`:1801` gates on `isinstance(node.value, str)`. `Q = b'SELECT a FROM bil_invoices'` → `exit=0 PASS` (`p5_sql.py`). psycopg accepts bytes query strings.

#### R1-F12 · **P2** · The anti-vacuity assertion is file-level only; a PASS can prove nothing, and prefixes have no minimum specificity

`_is_substantive` (`:1725-1731`) counts any `.py` with a non-docstring body, and `vacuous` (`:1822-1824`) triggers only when *no* substantive file exists. Reproducers (`/tmp/gate2_review_r1/p3_prefix.py`):

```
=== P3f vacuity: prefixes match nothing, trivial file (PASS?) :: exit=0
[module-deps] PASS — checked 2 subject(s)
=== P3e over-broad 1-char prefix 'a' (does it PASS?) :: exit=0
[module-deps] PASS — checked 5 subject(s)
  note: 0 unowned table identifier reference(s) (not flagged)
```

P3f: one module, `owned_table_prefixes: ["zzz_nothing_"]`, a single `X = 1` file → PASS with **zero** SQL strings and zero cross-module imports inspected. The report has no "N SQL-ish string(s) inspected / N cross-module import(s) resolved" note, so a positive-fixture PASS is indistinguishable from "nothing ownership-relevant existed". P3e: `owned_table_prefixes: ["a"]` is accepted (prefixes are validated only as identifiers, `:1437`), swallowing `account_ledger` and `anything_at_all` and reporting "0 unowned" with no disclosure that one module claims an unbounded namespace. This bears directly on the evidentiary weight of SCN-MOD001-006/-095.

#### R1-F13 · **P2** · `public_interfaces` entries are never checked to exist

`:1455-1461` validates shape and package-prefix only. `/tmp/gate2_review_r1/p8_manifest.py` case F: both modules declare non-existent interface paths, an import of one is approved, `exit=0 PASS`. A typo in an interface path therefore silently *widens* the approved surface instead of erroring — the opposite of the fail-closed posture applied to every other manifest field.

#### R1-F14 · **P2** · Evidence gap: SCN-MOD001-007's "raw table" half was never exercised

`knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-VERDICT-C-SCENARIO-EVIDENCE-2026-10-05.md` maps SCN-MOD001-007 ("a synthetic module directly importing another module's **raw table/ORM model**") to a single ORM-model import (`from app.modules.billing.models import Invoice`) and records "4/4 ... Criteria with gaps: 1 (scope note, not a gate defect)". The raw-SQL shape of `CROSS_DOMAIN_SQL_IMPORT` — a cross-domain *table* reference — is not exercised anywhere in the evidence set. That is precisely the shape R1-F01 and R1-F02 show to be weakest. This is an evidence-completeness gap, not a misrepresentation: the record's labeling, fixture-scoping disclosures and "no scenario PASS claimed" statements are accurate throughout, and every captured output I re-ran reproduced.

#### R1-F15 · **P3** · Duplicate violation reporting at one location

`/tmp/gate2_review_r1/p9_misc.py` C/D: one f-string and one `+` concatenation each yield **two** `MODULE_DEPS_SOURCE_UNINSPECTABLE` entries at the same `relpath:lineno` — once from `_uninspectable_for_node` and once from the dangling-keyword path, because `ast.walk` visits the inner `Constant` of a `JoinedStr` as well. Inflates counts; no dedup in `_finish`.

#### R1-F16 · **P3** · Docstring states the `_shared` rule backwards

`:196-200`: "any import FROM `_shared` INTO a domain module is `CROSS_DOMAIN_SQL_IMPORT`". Read naturally that says *a domain module importing `_shared`* is a violation; the code allows that (`:1790`) and flags the opposite edge (`:1697-1703`). The code is right and matches architecture.md control 3 — verified by probe (`p9_misc.py` F/G: `_shared` → module's public interface and `_shared` raw SQL on a module's table both FAIL; module → `_shared` passes). Fix the sentence.

#### R1-F17 · **P3** · No path normalization of `--modules-dir`

`/tmp/gate2_review_r1/p8_manifest.py` case H: a trailing slash and `/.` work, but `.../app/modules/../modules` and a case variant `app/MODULES` both produce `MODULE_DEPS_GATE_INPUT_INVALID` with a confusing *public_interfaces* message, because `_modules_root_package` (`:1486-1498`) walks un-normalised parents. Fails closed, so cosmetic — but a `Path.resolve()` would avoid a misleading diagnostic on a semantically identical path.

#### R1-F18 · **P3** · Dot-directories inside a module are pruned with no disclosure

`:1523-1525`. `/tmp/gate2_review_r1/p4_coverage.py` case E: a violating file in `membership/.hidden/` → `exit=0 PASS`. Low exploitability (a dot-named directory is not an importable package), but the report should still count pruned paths.

#### R1-F19 · **P3** · "Ruff clean" is against ruff's *default* rule set, not a project profile

There is no root `pyproject.toml`/`ruff.toml`; `line-length = 100` lives only in `backend/pyproject.toml`, which does not govern `tools/`. `backend/.venv/bin/ruff check --show-settings` resolves `project_root` to the repo root with no config file, so the clean result is against ruff's built-in defaults (E4/E7/E9+F), under which `E501` is not selected at all. `ruff check --select E501 tools/validate_architecture_gates.py tools/tests/...` reports **299 errors** (at ruff's default 88-column width). Verdict D item 3's "clear the 3 Ruff findings, do not mass-fix the 12 E501" was honored, but the resulting "All checks passed!" baseline is weaker than it reads and the E501 count is not reproducible without pinning both config and line-length.

#### R1-F20 · **P3** · Violation ordering is reverse-lexicographic while `checked` is sorted

`_walk_module` uses a LIFO stack (`:1521`), so subdirectory violations emit in reverse order. Deterministic across runs (`/tmp/gate2_review_r1/p11_final.py` B: 1 distinct signature over 3 runs; order `['a/top.py:1','a/sub3/v.py:1','a/sub2/v.py:1','a/sub1/v.py:1','a/sub0/v.py:1']`), but inconsistent with `_finish`'s `sorted(checked)` and awkward for diffing CI output.

#### R1-F21 · **P3** · Standard quoted identifiers and inline SQL comments force ERROR

`/tmp/gate2_review_r1/p10_schema.py`: `FROM "bil_invoices"` → exit 2, and `FROM /*x*/ bil_invoices` → exit 2, both via the dangling-keyword heuristic. Fails closed (correct direction), but ordinary ANSI SQL is treated as uninspectable, which will push authors toward the unquoted form that R1-F01 shows is also evadable.

### 5. Per-attack-surface coverage

| # | Surface | Probed | Result |
|---|---|---|---|
| 1 | Effective longest-prefix ownership | **Yes** — `p3_prefix.py`, `p10_schema.py`, `p11_final.py`, `p8_manifest.py` H | **Mixed.** Verdict C's three cases all correct. Longest-match resolution correct for same-module nesting; cross-module overlap provably complete (any identifier matched by two prefixes implies one prefix is a string-prefix of the other, which `:1463-1475` catches). No naive-`startswith` bug on module names (`pos` vs `pos_extra` both directions correctly attributed) or on interface paths (`apiv2` vs `api` correctly rejected). **Broken** on identifier normalization (R1-F01), module-name validation (R1-F08), prefix specificity (R1-F12). macOS case-insensitivity fails closed in all three shapes I tried (dir-vs-manifest case mismatch, uppercase manifest name, mixed-case import target). `..`/trailing-slash/`.` handled per R1-F17. Symlinks ERROR everywhere (module entry, nested file, manifest). |
| 2 | Raw SQL / ORM import detection gaps | **Yes** — `p5_sql.py` (21 cases), `p6_imports.py` (22 cases) | **Static import detection solid**; aliased-library imports do not evade the SQL scan (string literals are scanned regardless of executor). **Real gaps:** R1-F02 (DDL/MERGE/COPY/LOCK/GRANT), R1-F05 (4 dynamic-import idioms + `exec`), R1-F06 (`.join`, verb-interpolated f-string), R1-F11 (bytes), base64-encoded SQL (out of any reasonable scope). **False positives:** R1-F10 (docstring prose → FAIL), R1-F21 (quoted idents / SQL comments → ERROR). Comments correctly inert. |
| 3 | Four directed-pair enforcement | **Yes** — `p2_pairs.py`, 8 runs | **Correct.** All four pairs match `TSD_MIRROR.md:1521-1570` exactly; each direction enforced independently; no undirected-edge bug. Allowed edges exit 0, all four reverse edges exit 1 with `REVERSE_EDGE_NOT_EVENT_DRIVEN` citing the one permitted direction. Reverse-via-internals correctly yields `CROSS_DOMAIN_SQL_IMPORT` (precedence as documented). |
| 4 | Uninspectable / dynamic fail-closed paths | **Yes** — `p7_failclosed.py`, 21 cases | **Mostly correct.** Syntax error, NUL byte, unsupported extension, missing/malformed/symlinked/directory/list manifest, duplicate JSON keys, empty `modules`, `version != 1`, `version: true`, missing modules-dir, modules-dir without `__init__.py`, symlink inside module → all ERROR exit 2 with a named code. Docstring-only module → INCONCLUSIVE exit 2 `MODULE_DEPS_GATE_VACUOUS`. Zero-byte `.py`/`.sql` → clean PASS (correct). **One defect:** R1-F07 (non-UTF-8 → crash, exit 1, no output). |
| 5 | Manifest spoofing / vacuity | **Yes** — `p3_prefix.py`, `p8_manifest.py` | Zero modules rejected; `_shared` as a manifest name rejected; duplicate domain/schema rejected; whole-package-as-interface rejected. **Gaps:** R1-F12 (no subject-level anti-vacuity; no prefix specificity floor), R1-F13 (interfaces unverified), R1-F08 (names unvalidated). **Verdict D compliance confirmed:** no `contracts/modules/ownership.json` exists, none was created, and the gate does not reach into the real tree for any fixture run — every probe ran green with no real manifest present. |
| 6 | Fixture-scoped input contract | **Yes** — all probes + default invocation | **Confined.** With explicit flags the gate touches only `--modules-dir`, `--module-manifest` and the parent chain walked by `_modules_root_package`; `REPO_ROOT` is used only for the two argparse defaults. Default invocation fails closed as Verdict A.4 predicted: `[module-deps] ERROR — MODULE_DEPS_GATE_INPUT_INVALID: module manifest .../contracts/modules/ownership.json missing or a symlink`, exit 2. Note the parent-chain walk will read `__init__.py` above a fixture root if one exists (naming only, not a leak). |
| 7 | Output / exit contract | **Yes** — `--json`, repeated runs, `p9_misc.py` | Exit mapping `PASS 0 / FAIL 1 / INCONCLUSIVE 2 / ERROR 2` (`:274`) correct on every path **except** R1-F07. `--json` is `sort_keys=True` with a stable schema; `checked` sorted; no error path produces exit 0. Violations are surfaced in full, not merely counted. **Defects:** R1-F07 (no output at all on crash), R1-F09 (real violations withheld when uninspectable fires), R1-F15 (duplicates), R1-F20 (ordering). Vestigial `inventory: []` appears in module-deps JSON — harmless. |

### 6. Scenario mapping (code assurance only — no promotion, no sign-off)

I am not promoting or signing off any scenario. This is a code-assurance read of whether the implementation can support each criterion.

| Scenario | Criterion | Code assurance | Evidence |
|---|---|---|---|
| **SCN-MOD001-006** — synthetic module importing only its own prefix / approved interface → PASS | Positive path produces PASS | **Supported, with a caveat.** My independent fixture reproduced PASS exit 0 (`p1_baseline.py` P1a: own-package import + `SELECT id FROM mem_members` + a permitted §6.3 edge). Caveat: R1-F12 — a PASS does not evidence that any ownership-relevant subject was inspected, and the report carries no subject-level counter. |
| **SCN-MOD001-007** — module importing another module's raw table/ORM model → `CROSS_DOMAIN_SQL_IMPORT` citing both modules | ORM-model half | **Supported.** `p1_baseline.py` P1c: `CROSS_DOMAIN_SQL_IMPORT: membership -> billing — 'membership' (domain COM-01) imports 'billing' (domain COM-03) internal path 'app.modules.billing.internals' at membership/service.py:1`. Both modules, both domains, resolved path and `relpath:lineno` all present. |
| | Raw-table half | **NOT supported as a reliable denial.** `p1_baseline.py` P1d produces the correct denial for a bare identifier, but R1-F01 shows `public.`-qualification or upper-casing makes the identical violation PASS, and R1-F02 shows DDL/`MERGE`/`COPY` forms PASS. R1-F14: the raw-table half is also unexercised in the evidence set. This is the specific reason the verdict is BLOCKED. |
| **SCN-MOD001-095** — one §6.3 pair, permitted direction only → PASS | Permitted direction passes | **Supported, exceeded.** All four pairs verified independently by me (`p2_pairs.py`), not just one. Same R1-F12 caveat on PASS strength. |
| **SCN-MOD001-096** — same pair, reverse direction → `REVERSE_EDGE_NOT_EVENT_DRIVEN` | Reverse direction denied, citing the permitted direction | **Supported, exceeded.** All four reverse edges denied with the correct code and the correct permitted direction named (`p2_pairs.py`). `BIDIRECTIONAL_PAIRS` (`:1351-1356`) matches `TSD_MIRROR.md:1521-1570` exactly and is non-manifest-configurable as claimed. |

**Verdict C / Verdict D compliance (the decision record is binding here):** all three Verdict C cases are implemented exactly as decided, nothing exceeded or narrowed — same-module nesting ACCEPTED (`p3a` PASS), cross-module overlap ERROR with no exception path (`p3b`, `p3d`), exact duplicate ERROR with a named message (`p3c`: `module 'cal' has duplicate owned_table_prefixes entry 'cal_'`). The `if mod_a == mod_b: continue` narrowing at `:1469-1470` carries the Verdict C rationale inline. Verdict D items 1-3 verified: the duplicate check and both prefix tests exist (`test_validate_architecture_gates.py:1495`, `:1524`, `:1546`), the in-file "ASSUMPTION" comment is replaced by a citation of the decision record (`:1496`), the docstring states all three cases (`:179-191`), and Ruff is clean (subject to R1-F19). Item 5 verified independently: there is **no** `.github/workflows/` directory and no committed CI configuration, so Verdict A.4's premise is moot exactly as the implementation record states. **No instance of the implementation exceeding, contradicting or silently narrowing the governing decision.**

### 7. Tests and mutants actually executed

Everything below I ran. Where I only read code, I say so.

**Re-run of the claimed baseline** (from `/Users/ahmadmabrouk/Desktop/Veyro`):

```
backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q   → 90 passed in 1.68s
backend/.venv/bin/python -m pytest tools/tests/ -q                                      → 163 passed in 2.24s
backend/.venv/bin/ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
                                                                                        → All checks passed!
```

All three claims reproduce exactly (90/90, 163/163, Ruff clean). See R1-F19 for what "Ruff clean" does and does not mean here.

**Adversarial probes written and run** (all under `/tmp/gate2_review_r1/`, invoking the gate as a subprocess against synthetic fixtures — no real member data, no network, no tracked file touched):

| Script | Cases | What it established |
|---|---|---|
| `harness.py` | — | Fixture builder + subprocess runner |
| `p1_baseline.py` | 4 | Positive, reverse edge, internal import, cross-domain SQL all behave as documented |
| `p2_pairs.py` | 8 | All four §6.3 pairs, both directions, enforced independently |
| `p3_prefix.py` | 6 | Verdict C cases 1-3 correct; over-broad prefix and prefix-matches-nothing both PASS (R1-F12) |
| `p4_coverage.py` | 6 | R1-F03, R1-F04, R1-F18; nested dirs and `tests/` correctly scanned |
| `p5_sql.py` | 21 | R1-F02, R1-F06, R1-F10, R1-F11; implicit literal concat correctly caught |
| `p6_imports.py` | 22 | R1-F05; 10 import shapes correctly caught incl. `_shared` laundering and the `apiv2` trap |
| `p7_failclosed.py` | 21 | R1-F07; 18 malformed-input paths confirmed fail-closed |
| `p8_manifest.py` | 10 | R1-F08, R1-F13, R1-F17; case-insensitivity fails closed |
| `p9_misc.py` | 8 | R1-F08 (confirmed misattribution), R1-F07 `--json`, R1-F09, R1-F15; `_shared` rules correct |
| `p10_schema.py` | 8 | **R1-F01** (P0) |
| `p11_final.py` | 5 | Sibling module names correct; output ordering deterministic (R1-F20) |

**Coverage check of the existing suite** (`grep` over `tools/tests/test_validate_architecture_gates.py`): no test exercises `public.`-qualified or case-shifted table identifiers, DDL/`MERGE`/`COPY`, `str.join`-assembled SQL, `from importlib import import_module`, `builtins.__import__`, `exec`, a non-UTF-8 source file, a file at the modules-dir root, or a namespace-package directory. The 90 passing tests are genuinely informative about the paths they cover — they simply do not reach any of the P0/P1 surfaces above, which is why a green suite is not evidence here.

**Read, not executed:** `TSD_MIRROR.md` §6.3 (lines 1521-1575) and §24.1 (11595-11620) against `BIDIRECTIONAL_PAIRS`; `SCENARIOS.md` criteria at lines 405-412 and 1894-1905; the governing decision record in full; the three implementation records; `GATE2-VERDICT-C-SCENARIO-EVIDENCE` captured outputs compared against equivalent independent runs.

### 8. Limitations

- **The two files are untracked WIP**, so the change could not be diffed against a prior committed state. "NEW vs RECURRING" is established from the absence of any prior gate-2 review in `evidence/code-review/`, not from version history.
- **Real-tree behavior is unverifiable by design.** No `contracts/modules/ownership.json` exists (owner-blocked per Verdict A), so every functional probe is fixture-scoped. R1-F03's real-tree relevance rests on the *existence* of `backend/app/modules/conftest.py`, not on a real-tree run.
- **R1-F08 requires a manifest shape that cannot be authored today.** It was demonstrated on a synthetic manifest; it is a latent defect, not a currently-live one.
- **Filesystem-specific results.** All probing ran on case-insensitive APFS. Case behavior on a case-sensitive filesystem (Linux CI) was not tested and may differ; expected to be stricter, not looser.
- **Fixture-containment was established by code reading plus the absence of a real manifest**, not by syscall tracing. No `dtruss`/`fs_usage` run to prove no file outside the fixture tree was opened.
- **Not re-verified:** TSD Appendix I / DOM-001 (the implementation record flags this itself), ADR-009/ADR-010 contents, EIP §4.3 — all out of this dispatch's bounds.
- **No remediation attempted, no fix proposed in code.** Severity assignments are the reviewer's; the P0-vs-P1 line on R1-F04 (namespace packages) is arguable and the case for both is stated.

### 9. Model / session proof

- **Model identity:** Opus 5 (1M context), exact model ID `claude-opus-5[1m]`.
- **Independence:** fresh, independent context. The reviewer did not author, edit or advise on `tools/validate_architecture_gates.py`, its tests, or any of the gate-2 implementation or decision records. The governing decision record was treated as binding input and the implementation records as claims to verify. No message from any agent in this dispatch was treated as approval or consent.
- **Date:** 2026-10-05.
- **No code edits.** Every reviewer-created artifact lives under `/tmp/gate2_review_r1/`. Zero changes to `tools/`, `backend/`, `knowledge/` or any tracked file. No commit, no stage, no push, no network, no paid service, no real member data, no deploy.
- **Snapshot hashes re-verified after all probing and still match** (§2).
- **`git status --porcelain`** returned **352 entries**, identical to the pre-existing working-tree state recorded at session start (34 ` M` tracked modifications plus untracked WIP). Both review targets remain untracked, as the decision record states. No entry references `/tmp/gate2_review_r1` or any reviewer-authored file.

---

**Reviewer's recommended routing (not a decision — the lead's call):** R1-F01 (P0) and R1-F02, R1-F03, R1-F04, R1-F05, R1-F06, R1-F07, R1-F08 (P1) should be adjudicated before SCN-MOD001-006/007/095/096 go to scenario review, since R1-F01/F02 bear directly on whether SCN-MOD001-007's denial is reliable. R1-F01 and R1-F02 are the two the reviewer would not defer under any framing: they are silent exit-0 passes on the gate's headline invariant. R1-F13 and R1-F08 argue for the gate-2 input-contract ADR that Verdict B routes to the lead's own next dispatch — module-name validation and interface-existence belong in that contract.

---

## Orchestrator closing notes

- **Verdict recorded:** BLOCKED — P0=1, P1=7, P2=6, P3=7.
- **No self-remediation performed.** No code was edited, staged, committed or pushed by the top-level session or the reviewer.
- **Scenario review remains separate and unperformed.** This document is code assurance only; SCN-MOD001-006/007/095/096 are neither promoted nor signed off, and `veyro-scenario-reviewer` has not been dispatched.
- **`REVIEW_IN_FLIGHT.md`:** the prewritten `current_claim` was honored and was not overwritten or cleared by this review. Clearing remains the orchestrator's action once this result is recorded in the relevant durable files per that file's own protocol.
- **Round counters:** this unit's completed-round count becomes 1. SCN-MOD001-070 (5) and DOM-002 (4) untouched.

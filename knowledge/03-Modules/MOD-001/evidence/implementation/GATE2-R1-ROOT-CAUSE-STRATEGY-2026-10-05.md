---
doc: GATE2-R1-ROOT-CAUSE-STRATEGY
module: MOD-001
work_unit: GOV-01-R04 — TSD §24.1 gate 2 (module-dependency / cross-domain SQL lint)
scenarios_in_scope: SCN-MOD001-006, SCN-MOD001-007, SCN-MOD001-095, SCN-MOD001-096
authoring_role: veyro-lead (architecture / critical-engineering *decision* role)
authoring_model: claude-opus-5[1m] — Opus 5 (1M context)
date: 2026-10-05
input: GATE2-MODULE-DEPS-CODE-REVIEW-ROUND1-2026-10-05.md (BLOCKED, P0=1/P1=7/P2=6/P3=7)
type: DECISION / STRATEGY — not an implementation, not a review, not an ADR, no scenario promotion
---

# Gate-2 round-1 root cause and bounded remediation strategy

## 0. Scope of this dispatch (explicit)

**Did:** read the governing baselines (`verify_baselines.py` → PASS 4/4, all four
hashes match `PROJECT_INDEX.md`), `SESSION_BOOTSTRAP.md`,
`REVIEW_IN_FLIGHT.md` (`current_claim: CLEAR`), the round-1 review in full,
`GATE2-ARCHITECTURE-DECISION-2026-10-05.md` in full, the gate-2 source paths of
`tools/validate_architecture_gates.py`, `TSD_MIRROR.md` §24.1 / §6.3,
`SCENARIOS.md` SCN-MOD001-006/007/095/096, `CAPABILITY_POLICY.md` and
`CAPABILITY_REGISTRY.md` (CAP-001…CAP-008 only), `backend/pyproject.toml`, and
the `activeDistinctUnit` findings ledger in `AUTONOMOUS_CONVERGENCE_STATE.json`
(R1-F01…R1-F21 confirmed durable there, under `activeDistinctUnit`, **not** the
top-level `findings` array — that array holds the four DOM-002 fingerprints and
was not touched).

**Did not:** write or edit any source, test, config, CI, or contract file; create
`contracts/modules/ownership.json`; assign any of the six scaffolds to a domain;
author an ADR; dispatch any agent; claim or clear `REVIEW_IN_FLIGHT.md`; run the
gate or its tests; touch SCN-070 or DOM-002 counters or state; promote any
scenario. The only file written is this one. No paid service, no real member
data, no deploy.

---

## 1. Verdict

**CONFIRM the round-1 BLOCKED verdict. The remediation is NOT a widening of the
existing regex/name lists. It is a polarity inversion of four analysis paths from
"recognise-known-bad, else PASS" to "prove-clean, else VIOLATION or ERROR",
enforced by four runtime totality invariants and pinned by an evasion corpus that
asserts an exact outcome code per row.**

**Classification: ENGINEERING CHOICE throughout.** Every change below touches
only (a) the gate's analysis logic and (b) the *fixture-scoped* input schema.
Nothing below asserts that any real directory under `backend/app/modules/` owns
any domain or table prefix. The owner-reserved item from
`GATE2-ARCHITECTURE-DECISION-2026-10-05.md` Verdict A is unchanged, still
blocked, and is **not** on this path.

**Also decided: no third-party SQL parser is introduced.** See §5.

**Scenario status unchanged:** SCN-MOD001-006/007/095/096 remain NOT EXECUTED and
unpromoted. No code assurance, no scenario PASS, and no approval is expressed or
implied by this record.

---

## 2. Root cause

The twenty-one findings are not twenty-one defects. They are four structural
causes with twenty-one observable shapes. Extending `_SQL_DML_RE`,
`_is_dynamic_import_call`'s name list, or `_uninspectable_for_node`'s shape list
would move each shape without removing any cause — which is precisely the
failure mode SCN-070's convergence assessment already recorded on a different
surface (a same-invariant fail-open surviving a remediation).

### RC-1 — The analysis paths have a fourth terminal state: "unrecognised ⇒ PASS"

The gate's documented contract (`:24-31`, `:234-247`) has three terminal states:
PASS, FAIL (named violation), ERROR (unusable/uninspectable). The implementation
has a fourth, undocumented one: *unrecognised input falls out of every branch and
lands in PASS*. Four distinct fall-throughs, each a silent exit 0:

| Fall-through | Site | Shapes |
|---|---|---|
| `_resolve_owner` returns `None` ⇒ "unowned", not flagged, benign note | `:1594-1608`, `:1644-1653` | **R1-F01(a)**: a schema-qualified identifier never consults `owned_table_prefixes`, so `public.bil_invoices` is unowned while `bil_invoices` is a violation. `db.sb.bil_invoices` is mis-captured as `db.sb` by `_TABLE_IDENT_RE`'s two-segment ceiling. |
| `startswith` is byte-exact while `_TABLE_IDENT_RE` captures case-insensitively | `:1369-1371`, `:1606` | **R1-F01(b)**: `BIL_INVOICES` is captured verbatim, matches no lowercase prefix, resolves to `None`. PostgreSQL folds unquoted identifiers, so both spellings address one table. |
| `_is_sql_ish` requires one of five DML verbs, else `_scan_sql_text` returns `[]` | `:1373`, `:1585-1586`, `:1634-1635` | **R1-F02**: `CREATE`/`ALTER`/`DROP`/`MERGE`/`COPY`/`LOCK TABLE`/`GRANT`/`WITH` statements are never scanned at all. **R1-F11**: `bytes` literals are never considered (`:1801` gates on `isinstance(..., str)`). |
| The "closed set" of unprovable constructs is bound to literal names and AST shapes | `:1656-1665`, `:1668-1690` | **R1-F05**: `from importlib import import_module`, an alias, `builtins.__import__`, `getattr(importlib, …)`, `exec` all PASS. **R1-F06**: `str.join`, a fragment list, and a verb-interpolated f-string all PASS. |

The docstring at `:1668-1670` claims this set is "never extended with an 'etc.'
case". That is true of its *text* and false of its *effect*: a closed deny-list
over an open input space is an allow-list by default. The invariant the gate
exists to protect (TSD §24.1: "cross-domain raw SQL/ORM imports fail CI") cannot
be carried by a deny-list.

### RC-2 — Scan coverage is an inclusion heuristic, never reconciled against the tree

`run_module_deps_gate` builds `scan_dirs` from `_discover_modules`' output plus
`_shared` (`:1748-1751`) and walks only those. Nothing ever asks "is every file
under `--modules-dir` accounted for?" So three categories are invisible *with no
note, no count and no ERROR*: files at the modules-dir root (**R1-F03** —
`backend/app/modules/conftest.py` exists in the real tree today), directories
without `__init__.py` (**R1-F04** — importable since PEP 420, so deleting one
empty file removes a package from the gate's view at zero functional cost), and
pruned dot-directories (**R1-F18**). The tool applies closed-set discipline to
file *extensions* (`_categorize:1537-1546`, unknown suffix ⇒ ERROR) and none at
all to file *location*. A PASS therefore cannot be distinguished from "not
looked at" — the same evidentiary defect as **R1-F12**.

### RC-3 — The error taxonomy has one funnel, and the I/O layer bypasses it

`GateInputError` → ERROR/2 is the funnel (`:1806-1808`). `path.read_text()` at
`:1770` and `:1774` raises `UnicodeDecodeError`/`OSError` outside it, so the
process dies with **exit 1 and zero stdout** (**R1-F07**) — the exit code that
means "a violation was found", with no report and an empty `--json`. A
`# -*- coding: latin-1 -*-` file is legal Python, so this needs no adversary.
This is a *local inconsistency with the file's own convention*, not a missing
convention: `_load_json` (`:1265-1271`) catches `OSError, UnicodeDecodeError,
ValueError, RecursionError`, and the RLS gate (`:805-808`) already runs the exact
broad funnel with the right comment — *"fail closed: any read failure is ERROR,
never 'empty'"*. The module-deps gate simply does not use it.

### RC-4 — The manifest validates every field except its primary key, and validates shape without existence

`parse_module_manifest` (`:1409-1461`) checks `domain` against `_DOMAIN_CODE_RE`,
prefixes and schemas against `_MODULE_NAME_IDENT_RE`, interfaces against
`_INTERFACE_PATH_RE` and the own-package prefix — and checks the dict **key**
only for `!= "_shared"`. Combined with target resolution taking the first dotted
segment (`:1788-1789`), a declared module named `pos.v2` is resolved as a
*submodule of `pos`'s public interface*, so another module reads `pos.v2`'s
internals with a PASS (**R1-F08**). Separately, `public_interfaces` entries are
never checked to exist, so a typo *widens* the approved surface instead of
erroring (**R1-F13**) — the inverse of the posture applied to every other field.
And `owned_table_prefixes` has no specificity floor, so `["a"]` is accepted and
silently claims an unbounded namespace (**R1-F12**).

### Why RC-1…RC-4 are one cause

All four are the same error: *an unknown is treated as benign*. RC-1 on input
syntax, RC-2 on input extent, RC-3 on input readability, RC-4 on input identity.
The remediation is one principle applied four times, and the acceptance test for
the remediation is not "these 21 shapes now fail" but "the unknown state no
longer reaches PASS".

---

## 3. Parsing and security boundary (stated, because it sizes the fix)

**What gate 2 is.** A static architecture-hygiene lint over a tree whose authors
are trusted-but-fallible, run in CI. Its job is to make cross-domain coupling
*expensive and visible*, and to produce honest evidence about what it examined.

**In scope, and must close:** accidental cross-domain coupling; convenient
coupling by a developer or an agent; CI-configuration bypass (`GOV-01-R04`
requires that no gate be bypassable at the CI-workflow layer); and — decisively
for this remediation — **any trivial, zero-cost, semantics-preserving edit that
turns a denial into a PASS**. R1-F01, R1-F02, R1-F04, R1-F05 and R1-F06 are each
exactly that: one token, no functional price, silent exit 0. These are not
"hardening nice-to-haves"; they are the gate failing at its stated job.

**Explicitly out of scope, and must be disclosed on the face of the report:**
gate 2 is **not a security boundary**. Anyone with commit rights can defeat any
static lint — base64/`eval`, SQL assembled from database-sourced strings, SQL
reaching the DB from outside the tree, ORM reflection, a native extension. The
security boundary for tenant and domain isolation is gate 1 (RLS) plus database
grants, enforced at runtime by the engine; gate 2 is architecture hygiene layered
above it. This matters operationally in two ways. (1) We do not need provable
totality over arbitrary Postgres — so a hand-written analyser with an ERROR bias
is sufficient (§5). (2) The cost asymmetry is decisive: a false ERROR costs a
developer conversation, a false PASS puts a wrong claim into a module
certificate. **ERROR-on-unknown is therefore the correct bias, deliberately
chosen, at a known false-positive cost.**

**Hard rule on the analyser itself — unchanged and non-negotiable.** The gate
must never import, `exec`, `eval`, `compile`, or otherwise execute any file under
`--modules-dir`. `ast.parse` does not execute code; it must stay that way. This
is why a dynamic import can only ever be answered with ERROR and never with
"resolve it by running it", and why the dynamic-import branch must stay
fail-closed rather than becoming cleverer.

---

## 4. The four invariants (the actual deliverable)

These are runtime-asserted properties, not prose. Each has a named ERROR code and
at least one mutation control (§8).

**I-1 · SQL-TOTAL.** For any string (`str` or `bytes`) or `.sql` file that trips
the SQL trigger, the run terminates in exactly one of: ≥1 `CROSS_DOMAIN_SQL_IMPORT`
violation, ≥1 ERROR, or clean-with-≥1-attributed-table-reference. **"Tripped the
trigger but extracted zero table references" is ERROR, never PASS.** This single
clause is what ends the regex treadmill: the verb/keyword set becomes a *trigger
over-approximation* (broader ⇒ strictly more ERRORs ⇒ strictly safer) instead of
a *detector allow-list* (narrower ⇒ silent passes). Widening it can never weaken
the gate, so it can be widened freely and safely in future rounds.

**I-2 · ATTRIBUTION-TOTAL.** Every identifier in a table position resolves to
exactly one of six states, and the sixth is an ERROR, not a note:
1. owned by the importing module → clean, counted;
2. owned by another module → `CROSS_DOMAIN_SQL_IMPORT`;
3. bound locally in the same statement (a `WITH` CTE name, collected lexically) → clean, counted;
4. a reserved system identifier (fixed closed set: `pg_*`, `information_schema`, `pg_temp`) → clean, counted, disclosed;
5. declared in the manifest's new closed `external_table_references` list → clean, counted, disclosed by name;
6. **anything else → ERROR `MODULE_DEPS_TABLE_UNATTRIBUTED`.**

State 6 is the flip of `:1644-1647`'s "unowned ⇒ not flagged". It also gives
**defence in depth on R1-F01**: even if identifier normalisation (§6, F01)
regressed, `public.bil_invoices` would reach state 6 and ERROR rather than PASS.
Neither fix is relied upon alone. The round-1 rationale for not flagging unowned
identifiers ("CTEs, aliases, catalog tables") is answered by states 3–5 — it was
sound only because the gate could not tell those apart; once it can, the
rationale lapses.

**I-3 · COVERAGE-TOTAL.** A second, independent enumeration from the
`--modules-dir` root is reconciled against the union of the per-module walks, and
every path must land in exactly one bucket: discovered-module descendant,
`_shared` descendant, modules-root file, inert, pruned-and-counted, or
**unattributed ⇒ ERROR `MODULE_DEPS_UNATTRIBUTED_SOURCE`**. A reconciliation, not
a single traversal — so a discovery bug becomes an ERROR instead of a silent
omission. All bucket counts appear in the report, so a PASS is self-evidencing.

**I-4 · IO-TOTAL.** No exit path exists for "non-zero with no report". Every read
and decode goes through one `_read_source_bytes()`/`_read_source_text()` helper
that converts `OSError`/`UnicodeDecodeError`/`ValueError` into `GateInputError`
(the `_load_json:1265-1271` and `:805-808` convention, applied here), **and**
`main` gains an outermost funnel that maps any unexpected exception — current or
future — to a `GateReport(..., ERROR, [Violation("MODULE_DEPS_GATE_INTERNAL_ERROR", …)])`
that is still printed/serialised before exit 2. The funnel must not catch
`SystemExit`/`KeyboardInterrupt` and must never produce PASS.

**Cross-cutting prohibition, carried from SCN-070.** No `Path.exists()`,
`Path.is_dir()`, or `Path.is_file()` may gate *whether* a scan happens: those
return `False` on `EACCES` and reproduce exactly the fail-open shape that is the
live NON_CONVERGING item on the migration-ordering surface
(`SCN070-ROUND5-CONVERGENCE-ASSESSMENT-2026-10-05.md`). Directory and file
enumeration must surface `OSError` explicitly via I-4. Existing `is_symlink()` /
`is_dir()` *refusal* checks (`:1481`, `:1489`, `:1508`, `:1523-1533`) stay — they
fail closed in the right direction; the prohibition is on using them to decide to
skip.

---

## 5. SQL analysis: no new dependency — decided, with its limitation stated

**Decision: implement a bounded, in-tree SQL *lexer* behind one narrow internal
interface. Do NOT add `sqlglot`, `pglast`, or `sqlparse`.**

Grounds:

1. **A third-party parser is a capability, not a free import.** `sqlglot`,
   `sqlparse` and `pglast` are all absent from `backend/.venv` (verified).
   `CAPABILITY_POLICY.md` puts third-party capabilities at `review_status:
   PENDING` and "non-usable on real work until independently evaluated and
   qualified", with no exemption for non-first-party components; CAP-008
   (Docker/Colima/Postgres) is the live precedent for what that actually costs —
   provenance and licence verification from upstream sources, hash/version
   pinning, a stage-4/5 drill, an independent Opus capability-security review, a
   90-day re-evaluation date, and a registry row — and **BUG-038** exists
   precisely because a tooling dependency was used before it was registered.
   Taking that path would gate SCN-MOD001-006/007/095/096 behind a capability
   qualification rather than behind engineering. That is the wrong trade for a
   lint that currently analyses only synthetic fixture SQL.
2. **A layering problem on top of it.** The only pinned dependency set is
   `backend/pyproject.toml` (`psycopg[binary]==3.3.6`); `tools/` has no
   dependency manifest of its own. Adding a repo-root tool's parser to the
   backend's runtime dependencies, or creating a second dependency surface,
   is a structural decision that should not be smuggled in as a bug fix.
3. **The dependency would not be what makes the gate sound.** Soundness comes
   from I-1/I-2 — ERROR on anything not confidently classified. A parser would
   reduce false ERRORs; it would not change the fail-closed property.

**What the lexer must do** (and is tractable at roughly 200–300 reviewable
lines): tokenise with correct handling of single-quoted strings, dollar-quoted
strings, `E''`/`U&''` prefixes, `--` line comments and `/* */` block comments
(nested), and double-quoted identifiers; split statements on top-level `;`;
recognise a **broad** statement-verb trigger set (`SELECT INSERT UPDATE DELETE
TRUNCATE MERGE COPY WITH CREATE ALTER DROP GRANT REVOKE LOCK CALL EXECUTE
REFRESH REINDEX VACUUM ANALYZE COMMENT`); collect `WITH <name> AS` CTE names at
depth 0; and extract identifiers in table positions after a broad positional
keyword set (`FROM JOIN INTO UPDATE TABLE ONLY TRUNCATE ON REFERENCES`) plus the
bare-verb forms. Identifier normalisation: strip double quotes and **preserve
case** for quoted identifiers; **casefold to lower** for unquoted ones (PostgreSQL
semantics — so quoted `"BIL_INVOICES"` is genuinely a different table and
correctly reaches I-2 state 6); resolve 1-part names by longest prefix match;
resolve 2-part names by `owned_schemas`, else by stripping a configured
`default_schema` (new manifest field, default `"public"`) and retrying the prefix
match, else system-schema, else state 6; **≥3-part names are ERROR** (a
cross-database reference is outside the ownership model — this also removes
`_TABLE_IDENT_RE`'s two-segment mis-capture).

**SQL dialect limitation — stated plainly, not buried.** A lexer resolves token
classes, not clause grammar. It will therefore ERROR on legitimate but
structurally unusual SQL (some sub-select and `LATERAL` shapes, `WITH RECURSIVE`,
operator sequences that resemble identifiers, psycopg placeholder fragments such
as `%s`/`$1` inside otherwise-valid text, and non-standalone query fragments).
Those ERRORs are correct under I-1 and acceptable **today** for one specific
reason: the only SQL in gate-2 scope is synthetic fixture SQL authored by the
evidence set itself, because real-tree ownership is deferred and owner-blocked.
That acceptance has an explicit expiry: **the real-tree activation path must
re-open the parser question**, since a real tree will contain fragments and
driver-specific SQL at a volume where ERROR-by-default becomes untenable. Recorded
as unresolved decision U-2 (§10) with its trigger, not silently deferred.

**Replaceability requirement.** The lexer sits behind one interface —
`_extract_table_refs(text: str) -> TableRefs | Uninspectable` — and the fail-closed
contract (I-1, I-2) lives in the *caller*, not in the lexer. If U-2 later adopts
a parser, only that one function is replaced and the evasion corpus (§8) is the
unchanged acceptance test for the replacement. We are deliberately not betting
the gate on any single analyser's completeness.

---

## 6. Response by finding — P0 and P1

| # | Sev | Root cause | Decided response | Invariant |
|---|---|---|---|---|
| **R1-F01** | **P0** | RC-1 | (a) Strip `default_schema` from 2-part identifiers and retry the prefix match; resolve `owned_schemas` first; ≥3 parts ⇒ ERROR. (b) Normalise identifier case per PostgreSQL semantics (unquoted ⇒ casefold; quoted ⇒ preserve). (c) **Independently**, `None`-attribution becomes `MODULE_DEPS_TABLE_UNATTRIBUTED` ERROR, so a normalisation regression cannot restore the silent PASS. All three required; none sufficient alone. | I-1, I-2 |
| **R1-F02** | P1 | RC-1 | Replace the 5-verb `_is_sql_ish` gate with the broad statement-verb trigger; extraction keyed to the broad positional-keyword set; and the I-1 backstop (triggered + zero refs ⇒ ERROR) so an un-enumerated verb form cannot pass silently. | I-1 |
| **R1-F03** | P1 | RC-2 | Modules-root files are **scanned**, not refused, under a reserved domain-free importer `_root` that owns no prefixes, schemas or interfaces: imports of another module's declared public interface are allowed, internals are `CROSS_DOMAIN_SQL_IMPORT`, the §6.3 pair check is inapplicable (no domain), and every attributed table reference is therefore cross-domain while every unattributed one is ERROR. Root-file count is reported. Rationale: ERROR is for the *uninspectable*, not the *inconvenient* — `conftest.py` is fully inspectable, and refusing it would create a permanent real-tree ERROR for a legitimate file while asserting nothing about ownership. | I-3 |
| **R1-F04** | P1 | RC-2 | A non-discovered directory under `--modules-dir` containing any non-inert file is `MODULE_DEPS_UNATTRIBUTED_SOURCE` ERROR. PEP 420 makes it an importable package claiming no declared ownership, which the existing contract already treats as ERROR for the `__init__.py` case ("a discovered module with no manifest entry is ERROR"); the distinction between the two is not architecturally meaningful. Subdirectories *inside* a discovered module are unaffected (already attributed to it). | I-3 |
| **R1-F05** | P1 | RC-1 | Three independent nets, all ERROR: (i) module-level binding analysis tracking names bound from `importlib`, `importlib.util`, `importlib.machinery`, `builtins`, `imp`, `pkgutil`, `runpy` (including `from … import …` and aliases), so the call-site match is binding-based rather than receiver-name-based; (ii) a token set that is import-capable regardless of receiver (`__import__`, `import_module`, `load_module`, `exec_module`, `module_from_spec`, `spec_from_file_location`, `SourceFileLoader`, `find_module`, `walk_packages`), plus `getattr`/`setattr` applied to a tracked binding; (iii) a blanket rule — **any `exec`, `eval`, or `compile` call anywhere in a scanned file is ERROR**, because its presence makes that file's import *and* SQL surface unprovable. Cost today is zero (the six scaffolds contain none) and the residual undecidability of Python dynamic dispatch is disclosed in the report's coverage note, not papered over. | I-1 |
| **R1-F06** | P1 | RC-1 | Generalise assembly detection from two AST shapes to a rule over *operands*: if any operand or element reachable from a `JoinedStr`, `BinOp(+/%)`, `Call(str.join / .format)`, `List`/`Tuple` passed to `join`, or `%`-formatting contains a trigger-tripping literal **or** the expression combines a trigger-tripping literal with a non-literal, it is ERROR. The I-1 backstop covers the remainder: a verb-interpolated f-string whose literal part names a table now trips the trigger via the *table keyword* and, having no extractable verb context, ERRORs rather than passing. | I-1 |
| **R1-F07** | P1 | RC-3 | Single `_read_source_*` helper funnelling every read/decode failure into `GateInputError`; plus the outermost `main` funnel emitting `MODULE_DEPS_GATE_INTERNAL_ERROR` at exit 2 with a rendered report and valid `--json`. Makes "exit 1, empty stdout" unreachable by construction for all current *and unforeseen* exceptions — the generalisation, not the single observed throw site, is the fix. | I-4 |
| **R1-F08** | P1 | RC-4 | Validate the manifest **key** with `_MODULE_NAME_IDENT_RE` (which already exists one line away), rejecting dotted and non-identifier names; additionally reject any module name that is a dotted or string prefix of another. Closes the `pos.v2`-as-`pos`-submodule misattribution at its source rather than at `:1788-1789`. | RC-4 |

---

## 7. Disposition of P2 and P3 — nothing deferred

**Governing rule applied:** no finding whose observable shape is a silent exit 0
may be deferred, and any deferral must be disclosed *on the face of the gate's own
report*, not only in a bug record. Applying it, **none of the thirteen P2/P3
findings is deferred.** Most are entangled with the P0/P1 work and are cheaper to
close inside it than to track.

| # | Sev | Disposition | Decision |
|---|---|---|---|
| R1-F09 | P2 | **CLOSE NOW** | Keep the conservative *status* (ERROR, exit 2) and fix the *disclosure*: the report carries both lists, partitioned (`violations` + `uninspectable`). The current design (`:1810-1811`) conflates the two and hands a module a lever to hide its real violations behind one f-string. |
| R1-F10 | P2 | **CLOSE NOW** | Exclude docstring positions (module/class/function `body[0]` `Expr` `Constant`) from SQL scanning; count and disclose the exclusion. This becomes *load-bearing* under I-1: English prose ("Select the row from bil_invoices…") would otherwise trip the broad trigger and ERROR, which is worse than today's false FAIL. Residual risk (SQL hidden in `__doc__` and executed dynamically) is itself caught by F05(iii) and is named in the coverage note. |
| R1-F11 | P2 | **CLOSE NOW** | Scan `bytes` constants: decode UTF-8, fall back to latin-1, decode failure ⇒ ERROR via I-4. |
| R1-F12 | P2 | **CLOSE NOW** | Two parts. (i) Specificity floor: `owned_table_prefixes` entries must match `^[a-z][a-z0-9_]*_$` — at least two characters before a mandatory trailing underscore — which rejects `["a"]` and matches the `mem_`/`bil_` convention the fixtures already use. (ii) Report counters (§9) so a PASS states what it inspected; file-level vacuity stays the gate's floor, and the *evidence set* must assert non-zero attributed-reference and resolved-edge counts for the positive fixtures. Deliberately **not** promoting zero-subject to INCONCLUSIVE in the tool: that would invent a new failure mode for a real tree we have not modelled. |
| R1-F13 | P2 | **CLOSE NOW** | Every `public_interfaces` entry must resolve to an existing `<module>/<path>.py` or `<module>/<path>/__init__.py`; otherwise `MODULE_DEPS_GATE_INPUT_INVALID`. A typo must narrow, never widen. |
| R1-F14 | P2 | **CLOSE NOW — mandatory** | This *is* SCN-MOD001-007's raw-table half and the exact surface R1-F01/F02 proved weakest. The regenerated evidence set must exercise it directly, and must carry the full evasion corpus (§8) as captured output. Not a deferrable gap. |
| R1-F15 | P3 | **CLOSE NOW** | Deduplicate `Violation` (frozen dataclass) in `_finish` while preserving first-seen order. |
| R1-F16 | P3 | **CLOSE NOW** | Correct the inverted `_shared` sentence at `:196-200`. Code is right; prose is backwards. |
| R1-F17 | P3 | **CLOSE NOW** | `Path.resolve()` on `--modules-dir`/`--module-manifest` **after** the existing `is_symlink()` refusals, so `../modules` stops yielding a misleading `public_interfaces` diagnostic. |
| R1-F18 | P3 | **CLOSE NOW** | Count pruned dot-directories and `__pycache__` and report them (required by I-3's accounting anyway). |
| R1-F19 | P3 | **CLOSE NOW** | An unreproducible lint claim is an evidence defect. Add a root `ruff.toml` pinning `line-length` and the selected rule set for `tools/`, then re-run and record the number. Per the prior Verdict D item 3, **do not** mass-fix the 12 `E501` in the same diff; record the pinned-config count as a known, reproducible figure. |
| R1-F20 | P3 | **CLOSE NOW** | Sort violations deterministically by `(code, subject, detail)` in `_finish`, consistent with its existing `sorted(checked)`. |
| R1-F21 | P3 | **CLOSES AS A CONSEQUENCE** | Quoted identifiers and inline SQL comments stop being ERRORs once the lexer handles them natively. This is itself an argument for §5's lexer over further regex work: it removes a false ERROR that today pushes authors toward the unquoted form R1-F01 shows to be evadable. |

**Deferred: nothing from R1.** Two items are *routed*, both pre-existing and
neither a round-1 finding: the gate-2 input-contract ADR (U-1) and real-tree
activation (owner-reserved, already blocked under Verdict A).

---

## 8. Negative and mutation controls (acceptance, not suggestion)

The implementation is accepted only against the controls below. The specification
is deliberately test-shaped so the implementer builds to a fixed contract rather
than re-deciding the design.

**C-1 · SQL evasion corpus.** One table-driven test, one row per spelling of a
single cross-domain reference to another module's owned table. Rows: bare;
`public.`-qualified; `UPPER`; `MiXeD`; double-quoted lower; double-quoted upper;
3-part `db.schema.table`; with an inline `/* */` comment; with a `--` comment;
inside a `WITH` CTE body; `MERGE INTO`; `COPY`; `INSERT INTO`; `DELETE FROM`;
`TRUNCATE`; `UPDATE … SET`; `CREATE TABLE`; `ALTER TABLE`; `DROP TABLE`;
`LOCK TABLE`; `GRANT … ON`; `REFERENCES`; `bytes` literal; implicit adjacent
literal concatenation; `str.join` of fragments; fragment list then runtime concat;
verb-interpolated f-string; `%`-format; `.format()`; dollar-quoted body.

**Each row asserts an exact outcome code, not merely "non-zero".** Rows that are
statically attributable must assert `FAIL` / `CROSS_DOMAIN_SQL_IMPORT`
specifically (so that deleting normalisation and landing in
`MODULE_DEPS_TABLE_UNATTRIBUTED` *fails the test* rather than passing it); rows
that are genuinely unprovable must assert `ERROR` with the specific code
(`MODULE_DEPS_SOURCE_UNINSPECTABLE` or `MODULE_DEPS_TABLE_UNATTRIBUTED`). A
blanket `exit_code != 0` assertion over every row sits alongside, not instead.

**C-2 · Import evasion corpus.** `importlib.import_module`; `from importlib
import import_module`; aliased `import importlib as il`;
`from importlib import import_module as im`; `builtins.__import__`;
`__import__`; `getattr(importlib, "import_module")`; `exec` of an import
statement; `eval`; `compile`; `importlib.util.spec_from_file_location` +
`module_from_spec`; `SourceFileLoader(...).load_module()`;
`pkgutil.walk_packages`; `runpy.run_module`. All ⇒ ERROR exit 2.

**C-3 · Coverage corpus.** A violating file planted at the modules-dir root
(`conftest.py`, `__init__.py`); in a `__init__.py`-less directory; in a dot-dir;
in a nested sub-package; in `_shared`. Each asserts the specific decided outcome
from §6 (scanned-and-flagged, `MODULE_DEPS_UNATTRIBUTED_SOURCE`, or
pruned-and-counted) and the expected bucket counters.

**C-4 · I/O corpus.** Non-UTF-8 `.py`; `latin-1` with a coding cookie;
non-UTF-8 `.sql`; a mode-000 file; a mode-000 directory inside a module; a
mode-000 modules-dir. **Every one: exit 2, a named code, non-empty stdout, and
valid JSON under `--json`.** The mode-000-directory rows are the specific
SCN-070 regression guard — they are the shape `Path.is_dir()`/`exists()` swallow.

**C-5 · Manifest corpus.** Dotted module name; non-identifier name; a name that
is a prefix of another; `owned_table_prefixes` of `["a"]`, `["ab"]`, `["ab_"]`
(reject, reject, accept); a non-existent `public_interfaces` entry; an unknown
`default_schema` type; an `external_table_references` entry that is not a
concrete identifier. Plus **re-assertion of the three Verdict C cases unchanged**
— same-module nesting ACCEPT, cross-module overlap ERROR, exact duplicate ERROR
— so this remediation provably does not regress the decision round 1 confirmed as
correctly implemented.

**C-6 · Mutation controls, reported per branch (not as an aggregate).** Each
mutation must be killed by at least one named test: (1) `MODULE_DEPS_TABLE_UNATTRIBUTED`
→ note; (2) remove the `_read_source_*` funnel; (3) remove the `main` outermost
funnel; (4) drop the I-3 reconciliation (or its unattributed bucket); (5) narrow
the statement-verb trigger back to five verbs; (6) remove identifier
normalisation; (7) remove the manifest `name` regex; (8) remove the I-1
"triggered + zero refs ⇒ ERROR" backstop; (9) revert `exec`/`eval`/`compile` to
allowed; (10) revert import detection to receiver-name matching; (11) re-fold
violations into the uninspectable short-circuit; (12) remove the prefix
specificity floor. A surviving mutant is a BLOCKER for the dispatch, not a note.

**C-7 · Anti-vacuity on the fixtures themselves.** Every corpus row must assert
that its fixture file actually contains the intended construct (read it back),
and each corpus must include the bare/control row that *does* produce the
expected denial. This is the R1-F12 lesson applied to the tests: a typo'd fixture
must not be able to produce a green row.

---

## 9. Report-surface requirements (so a PASS is self-evidencing)

Every module-deps run must disclose, in both text and `--json`: declared /
discovered / scanned module counts; files inspected, inert, pruned (by reason),
modules-root; docstrings excluded from SQL scanning; SQL-trigger strings
inspected; table references by I-2 state (own / other / CTE / system / declared
external); cross-module import edges resolved and approved; and a coverage note
naming what is **not** examined — out-of-tree SQL, ORM-reflected and driver-level
dynamic SQL, non-Python/non-`.sql` sources, docstring contents, the residual
undecidability of Python dynamic dispatch, the lexer's dialect limitation (§5),
and that **gate 2 is not a security boundary** (§3). The existing "input contract
not yet fixed by an ADR" note stays until U-1 lands.

---

## 10. Unresolved decisions (named, with owners and triggers)

| # | Decision | Status | Trigger / route |
|---|---|---|---|
| **U-1** | Gate-2 input-contract ADR (schema and semantics only; binds no real domain) — now larger than when Verdict B recommended it, since this strategy adds `default_schema`, `external_table_references`, the prefix specificity floor, module-name validation, interface-existence, and the `_root` reserved importer | **Not authored.** Deliberately out of this dispatch's bounds | A **separate** `veyro-lead` dispatch, before or concurrent with the first implementation dispatch. Still an ENGINEERING CHOICE needing no owner approval (a lint's input schema is not material product/pricing/business/scope architecture). Candidate: `ADR-011`, for ADR-010 parity |
| **U-2** | Whether to adopt a qualified third-party SQL parser (`sqlglot` leading candidate) | **Declined for now** (§5), with the limitation disclosed on the report's face | Re-open when real-tree gate-2 activation is unblocked, or when fixture SQL complexity makes ERROR-by-default untenable. Requires a `CAP-009` registry row and the full `CAPABILITY_POLICY.md` lifecycle (CAP-008 precedent, BUG-038 cause), plus a decision on where `tools/`' dependencies live |
| **U-3** | Whether gate 2 should join ADR-005 Decision 1's critical-slice list (currently: RLS lint and permission lint only) | **Not changed here.** Implementation routes to `veyro-implementer` (Sonnet) per the existing mapping and the prior Verdict D | A rerouting would be an ADR-005 amendment under DC-17's routing-change sub-clause; it will not be done silently. Risk acknowledged (§11) and mitigated by spec-tight dispatches plus a fresh Opus round-2 review |
| **U-4** | Whether the evasion corpora need their own scenario rows, or are code-assurance evidence under SCN-MOD001-007 | **Not decided here** — catalog design belongs to `veyro-scenario-reviewer` | Recommendation (non-binding): covered under SCN-007's existing acceptance text as mechanism evidence; no new rows. Raise at review stage 2 |
| **U-5** | `GATE2-ARCHITECTURE-DECISION-2026-10-05.md` A.4's CI premise — whether any committed workflow invokes `--gate module-deps` with repo defaults | Round 1 independently confirmed **no** `.github/workflows/` and no committed CI config exists, so the premise is moot today | Revisit when CI is first wired. Inventing a skip/exempt path remains forbidden |
| **OWNER** | Committing `contracts/modules/ownership.json` binding the six scaffolds to domain codes and owned table prefixes | **BLOCKED: OWNER_APPROVAL_REQUIRED** — unchanged by this record | Owner approval in `OWNER_APPROVALS.md` + an ADR per DC-09, or the architecture.md control-5 activation condition (first real source file landing in a scaffold). `payment` and `pos` additionally remain ungrounded in any verified baseline source |

### Engineering choice vs owner-reserved — the line, restated

The *fixture-scoped input contract* (manifest v1 schema, discovery rules,
normalisation semantics, `default_schema`, `external_table_references`, reserved
`_root`/`_shared` importers, `BIDIRECTIONAL_PAIRS` pinning) is a MOD-001
implementation artifact: it defines what a *hypothetical* manifest must look like
and binds no real directory to any domain. That is an ENGINEERING CHOICE, and
every item in §§4–9 stays inside it.

*Real-tree domain ownership* — any artifact asserting that
`backend/app/modules/payment` is COM-03, or that `membership` owns `mem_` — is
OWNER-RESERVED (material architecture change) and is not touched.

**One consequence to disclose now so it is never misread as a regression:** after
this remediation, a hypothetical real-tree run gains *new* ERROR surfaces
(unattributed table identifiers; any `__init__.py`-less package under
`backend/app/modules/`) on top of the existing missing-manifest ERROR. The real
tree is already ERROR by design and asserts nothing about ownership; these are
additional *fail-closed* paths, not new defects, and every evidence artifact must
continue to carry **"fixture-scoped; real-tree domain ownership DEFERRED"** on its
face.

---

## 11. Bounded next actions (sequencing only — nothing dispatched here)

1. **U-1 ADR** — separate `veyro-lead` dispatch. Fixes the input contract
   §§4–6 extend. No owner approval required; no real domain bound.
2. **D1a — SQL analysis totality.** `_extract_table_refs` lexer + I-1 + I-2 +
   manifest additions (`default_schema`, `external_table_references`, prefix
   floor, name validation, interface existence) + corpora C-1, C-5. Closes
   F01, F02, F06, F08, F10, F11, F12(i), F13, F21.
3. **D1b — coverage, imports, taxonomy, report.** I-3 reconciliation + `_root`
   importer + I-4 funnels + import binding analysis + report counters and
   partitioned disclosure + the mechanical P3s. Corpora C-2, C-3, C-4.
   Closes F03, F04, F05, F07, F09, F12(ii), F15, F16, F17, F18, F20.
4. **D2 — evidence and lint baseline.** Root `ruff.toml` pin and re-run (F19);
   regenerate the full fixture-scoped evidence set including SCN-007's
   raw-table half and the captured corpora (F14); each artifact labelled
   fixture-scoped. Then C-6 mutation controls reported per branch.
5. **Round-2 independent code review** — fresh `veyro-code-reviewer` (Opus) over
   the combined diff. `REVIEW_IN_FLIGHT.md` is `CLEAR` as of round 1's recording;
   a claim must be written **before** that dispatch call returns, per that file's
   protocol. This record is an *input* to that review, never an approval (DC-14).
6. **Then** `veyro-scenario-reviewer` for SCN-MOD001-006/007/095/096. No
   gatekeeper involvement (gate 2 is one of seven gates).

Out of scope for every dispatch above, explicitly: `contracts/modules/ownership.json`;
any domain binding; any CI change; any scenario promotion; any SCN-070 or DOM-002
state, counter, or file.

**Risk this strategy accepts, stated rather than hidden (U-3).** D1a/D1b are
substantial fail-closed analysis code authored at Sonnet tier, and the prior
guarded implementation attempt on this unit timed out leaving a broken tree
(`ast` undefined in `run_module_deps_gate`, per the convergence ledger). The
mitigations are: a fixed specification (this record plus U-1's ADR), so the
implementer implements rather than designs; two smaller dispatches instead of
one; per-branch mutation reporting as a hard acceptance gate; and a fresh Opus
round-2 review that is expected to author its own adversarial corpus
independently, as round 1 did.

---

## 12. Assumptions (labelled; not researched further within these bounds)

- **Verified this session:** baselines 4/4 (`verify_baselines.py` PASS, all four
  hashes match `PROJECT_INDEX.md`); `REVIEW_IN_FLIGHT.md current_claim: CLEAR`;
  R1-F01…R1-F21 durable in `AUTONOMOUS_CONVERGENCE_STATE.json` under
  `activeDistinctUnit`; `sqlglot`/`sqlparse`/`pglast` all absent from
  `backend/.venv`; no root `pyproject.toml`/`ruff.toml`/`*.cfg` exists;
  `backend/pyproject.toml` pins only `psycopg[binary]==3.3.6` plus dev tooling;
  the capability registry holds CAP-001…CAP-008 and no pip-library row; TSD
  §24.1 gate-2 and §6.3 text; the four scenario acceptance texts; the
  `:805-808` and `:1265-1271` broad-funnel precedents in the same file.
- **Taken from round 1 without independent re-execution:** every reproducer
  result, the 90/90 and 163/163 test counts, and the Ruff findings. I ran no
  tests and no probes — this dispatch is decision-only. Round 1 was independent,
  model-attested (`mr_verify.py` PASS 76/76 `claude-opus-5`), and reported
  snapshot hashes matching before and after probing, so its observations are
  treated as reliable inputs; they remain *its* observations, not mine.
- **Assumed, not verified:** EIP §4.3 / Appendix H exact text; ADR-005 and
  ADR-010 contents (taken from secondhand citation in `REQUIREMENTS.md`, the
  prior decision record and agent descriptions); `MODEL_ROUTING.md`'s exact
  per-role mapping; TSD Appendix I / DOM-001 (SCN-007 cites it; round 1 flagged
  it unverified and it stays unverified here); the complete TSD §10 domain
  roster. `CURRENT_STATE.md` and `CURRENT_HANDOFF.md` exceed the readable budget
  in full; governance state is taken from `CURRENT_HANDOFF.md`'s head,
  `REVIEW_IN_FLIGHT.md`, and the convergence ledger's `activeDistinctUnit`.
- **Severity scale unchanged.** I did not re-grade any round-1 severity. The
  P0/P1 set is adopted as given, and the P2/P3 set is closed rather than
  re-ranked.
- **Not a review and not an approval.** DC-14: this session's reasoning is not
  reviewer consent. No scenario is promoted; no gate is accepted; the round-1
  BLOCKED verdict stands until a round-2 independent review says otherwise.

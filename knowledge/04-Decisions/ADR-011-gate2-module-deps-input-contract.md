---
doc: ADR-011
status: DECIDED (2026-10-05) — conforming to the governing baseline; no owner approval required (see "Conformance determination")
date: 2026-10-05
decided_by: veyro-lead (registered architecture/ADR-decision role, fresh bounded adjudication dispatch; claude-opus-5[1m] — Opus 5 (1M context), as reported by this environment). Not the gate-2 implementer. No code, security, or scenario review approval is given or implied.
model_attestation: NONE RUN BY THIS SESSION. `mr_verify.py` was not run against this dispatch's own transcript — self-attestation of model identity is of little value and the tool is the orchestrating session's to run. The orchestrator should attest this dispatch's transcript if an attestation is wanted for the record. Stated rather than omitted.
amended: 2026-10-06 — AMENDED BY ADDENDUM (clause D6.7, extraction totality; D7.1 amended by
  reference; one false D8 disclosure sentence corrected). See "Addendum 2026-10-06" at the end
  of this file. The original decision text above that heading is preserved byte-unchanged; the
  front-matter `status`/`date`/`decided_by` lines below describe the ORIGINAL 2026-10-05
  decision and are deliberately not rewritten. Addendum authority: this ADR's own Follow-up
  delegation of ADR-011 gaps to `veyro-lead`, acting on round-2 finding R2-N02. No owner
  approval required.
module: MOD-001 (GOV-01-R04, TSD §24.1 gate 2 — module dependency / cross-domain SQL lint)
requested_by: knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-ARCHITECTURE-DECISION-2026-10-05.md Verdict B ("an ADR fixing gate 2's input contract — schema and semantics only, binding no real domain"), and GATE2-R1-ROOT-CAUSE-STRATEGY-2026-10-05.md U-1
adjudication: knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-QUALIFIED-LEAD-DECISION-2026-10-05.md (overall verdict ACCEPTED WITH MANDATORY CORRECTIONS; this ADR binds those corrections)
---

# ADR-011: Gate-2 (module-deps) input contract — fixture-scoped manifest v1 schema, identifier-attribution semantics, reserved importers, and the error taxonomy

## Scope limit — read this before anything else

**This ADR is SCHEMA AND SEMANTICS ONLY.** It binds the gate-2 *input
contract for fixtures*: what a manifest must look like, how an identifier
in a table position is attributed to an owner, which importer names are
reserved, and which outcome code every terminal state maps to.

**It binds NO real scaffold and NO domain logic.** Nothing in this ADR
asserts that `backend/app/modules/payment` is COM-03, that `membership`
owns `mem_`, or that any directory under `backend/app/modules/` owns any
table prefix, schema, or domain code. No `contracts/modules/ownership.json`
is authored, implied, or made authorable by this ADR. Real-tree domain
ownership remains **DEFERRED** and **`BLOCKED: OWNER_APPROVAL_REQUIRED`**
exactly as `GATE2-ARCHITECTURE-DECISION-2026-10-05.md` Verdict A left it;
this ADR does not touch that blocker and does not depend on it.

Every evidence artifact produced against this contract must continue to
carry **"fixture-scoped; real-tree domain ownership DEFERRED"** on its
face.

## Context

**The governing text, verified against the TSD docx itself** (extracted
from `Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx`, not only
from `TSD_MIRROR.md` — the mirror was confirmed faithful on both
passages):

> §24.1, architecture enforcement gates: *"Module dependency/SQL lint:
> application modules may reference only their owned table prefix/schema
> and approved read-model/application interfaces; cross-domain raw
> SQL/ORM imports fail CI. For the four intentional bidirectional pairs,
> §6.3 is the normative directed graph: only the listed synchronous edge
> may import/call the opposite application interface; the reverse edge
> must remain event-driven."*

> §6.3, rule: *"…only the synchronous direction listed above is allowed
> in the module import/application-call graph. The reverse edge is
> event-driven. CI dependency lint treats this table as the expected
> graph and rejects reverse synchronous imports **or direct
> repository/table coupling**."*

Two properties of that text size this ADR. First, it is written as an
**allow-list**: a module may reference *only* its owned prefix/schema and
approved interfaces. An identifier that is neither is therefore not
permitted, which means the gate may never let an unrecognised identifier
reach PASS. Second, §6.3's four pairs and their directions are
**normative**, which is why `BIDIRECTIONAL_PAIRS` is pinned in source and
is never manifest-configurable.

**What the baseline fixes and this ADR does not change:** the six
architecture gates and their order (§24.1); the four §6.3 pairs and their
permitted directions; `GOV-01-R04`'s acceptance that each gate has a
passing valid-fixture proof **and** a deliberate-violation fail-closed
proof, and that **no gate is bypassable at the CI-workflow-configuration
layer** (`REQUIREMENTS.md` 234-292); and `REQUIREMENTS.md`'s exclusion of
test *content* for domains that do not exist yet ("the gate exists and
blocks on it; content is later modules' job").

**What the baseline leaves open** — and what this ADR therefore fixes:
no manifest file format, schema, identifier-normalisation rule, schema
versus prefix precedence, reserved importer name, or outcome-code
vocabulary appears in the TSD, EIP, or design bundle. Those are
implementation-contract details inside an already-accepted architecture.
Deciding them is a `veyro-lead` call, per Verdict B's split, as long as
they stay inside the constraints above.

**Why now.** Gate 2's input contract has until now existed only as a tool
docstring, which is exactly why
`GATE2-MODULE-DEPS-REPAIR-CHECKPOINT-2026-10-05.md` §6 recorded that
"there is no authority this session could have checked the intent
against." Gates 1 and 4 have their contracts fixed by ADR-010 and
ADR-009. Round-1 independent code review
(`GATE2-MODULE-DEPS-CODE-REVIEW-ROUND1-2026-10-05.md`, **BLOCKED**,
P0=1/P1=7/P2=6/P3=7) then found that the gate's primary key — the module
name — and its interface paths were unvalidated (R1-F08, R1-F13) and
recommended that both "belong in that contract". The round-1 remediation
strategy additionally proposes new manifest fields and a widened
ownership space, which makes the contract larger than when Verdict B
recommended it. The adjudication of that strategy
(`GATE2-R1-QUALIFIED-LEAD-DECISION-2026-10-05.md`) accepted it **with
mandatory corrections**; this ADR is where those corrections become
binding.

## Decision

### D1 — Manifest file: `version` **1**, strict closed schema, JSON only

1. The gate reads exactly one manifest, supplied via `--module-manifest`
   (default `contracts/modules/ownership.json`). A symlinked manifest, a
   missing manifest, a non-object top level, or a list is **ERROR**
   `MODULE_DEPS_GATE_INPUT_INVALID`. Neither `--modules-dir` nor
   `--module-manifest` offers a skip, exempt, or allowlist path, and none
   may be added.
2. **`version` stays `1`.** It is a JSON integer equal to 1; a boolean is
   refused. The new fields in D2 are additive and optional-with-defaults,
   and **no committed manifest exists anywhere in the repository** (round
   1 independently confirmed the absence of
   `contracts/modules/ownership.json`), so there is no consumer to
   migrate. Bumping the version would assert a migration obligation that
   does not exist. Recorded explicitly so a future reader does not
   re-litigate it.
3. Strict JSON parsing: duplicate keys are an ERROR, nesting deep enough
   to exhaust the parser is an ERROR, and every read or decode failure is
   a structured ERROR, never an uncaught exception.
4. Unknown keys are refused at every level. Empty `owned_table_prefixes`
   and empty `public_interfaces` are refused. A duplicate `domain` and a
   duplicate `owned_schemas` entry across modules are refused.

### D2 — Module entry schema

```json
{
  "version": 1,
  "default_schema": "public",
  "modules": {
    "membership": {
      "domain": "COM-01",
      "owned_table_prefixes": ["mem_"],
      "owned_schemas": ["sm"],
      "public_interfaces": ["app.modules.membership.api"],
      "external_table_references": []
    }
  }
}
```

| Field | Required | Rule |
|---|---|---|
| `default_schema` | No, default `"public"` | Top-level, not per-module. A single lowercase identifier. Must **not** appear in any module's `owned_schemas` (D3.3) |
| module key (`name`) | Yes | Must fullmatch `^[a-z_][a-z0-9_]*$`. Dotted and non-identifier names are **ERROR**. Must not be a reserved importer name (D4) |
| `domain` | Yes | Fullmatch `^[A-Z]{3}-[0-9]{2}$`; unique across modules |
| `owned_table_prefixes` | Yes, non-empty | Each entry fullmatches **`^[a-z][a-z0-9_]+_$`** — note `+`, not `*`. Duplicates within a module are ERROR. Cross-module overlap is ERROR (Verdict C). Reserved values are ERROR (D3.4) |
| `owned_schemas` | No | Lowercase identifiers, unique across modules, disjoint from `default_schema`, reserved values ERROR (D3.4) |
| `public_interfaces` | Yes, non-empty | Fullmatch `^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+$`, prefixed by the module's own package, and **each must resolve to an existing `<module>/<path>.py` or `<module>/<path>/__init__.py`**; otherwise ERROR. A typo must narrow the approved surface, never widen it (closes R1-F13) |
| `external_table_references` | No, default `[]` | Concrete identifiers only, no wildcards. **Constrained by D3.5 — this is not an allowlist** |

**Why the prefix floor is `+` and not `*`.** The intent is "at least two
characters before a mandatory trailing underscore". `^[a-z][a-z0-9_]*_$`
does **not** implement that intent — it accepts `a_`, confirmed by direct
execution during adjudication. `^[a-z][a-z0-9_]+_$` rejects `a`, `ab`,
and `a_`, and accepts `ab_`, `mem_`, `bil_`. A one-character prefix
silently claims an unbounded namespace (R1-F12).

**Module-name validation alone closes R1-F08, and nothing more is
added.** With dots excluded from the key, target resolution's
`remainder.split(".", 1)[0]` can only ever yield a declared top-level
name, so the `pos.v2`-as-`pos`-submodule misattribution is closed at its
source. A proposal to additionally reject any module name that is a
string prefix of another is **rejected**: round 1 verified `pos` versus
`pos_extra` is already attributed correctly in both directions, so the
ban would reject a legal, correctly-handled configuration. A *directory*
named `pos.v2` is already fail-closed — it becomes a discovered module
with no manifest entry, which is ERROR.

### D3 — Identifier attribution semantics (the heart of this contract)

**D3.1 — Normalisation (PostgreSQL semantics).** Unquoted identifiers are
casefolded to lower case; double-quoted identifiers **preserve case** and
have their quotes stripped. Quoted `"BIL_INVOICES"` is therefore genuinely
a different table from `bil_invoices` and correctly reaches D3.2 state 6.
This closes R1-F01(b): `startswith` may never again be byte-exact against
a case-insensitively captured identifier.

**D3.2 — Every identifier in a table position resolves to exactly one of
six states. The sixth is an ERROR, not a note.**

| State | Condition | Outcome |
|---|---|---|
| 1 | Owned by the importing module | clean, counted |
| 2 | Owned by another module | **FAIL** `CROSS_DOMAIN_SQL_IMPORT`, naming both modules and both domains |
| 3 | Bound locally in the same statement (a `WITH` CTE name, collected lexically at depth 0) | clean, counted |
| 4 | A reserved system identifier (D3.4) | clean, counted, disclosed |
| 5 | A declared `external_table_references` entry (D3.5) | clean, counted, **disclosed by name** |
| 6 | **Anything else** | **ERROR** `MODULE_DEPS_TABLE_UNATTRIBUTED` |

State 6 is the inversion of the previous "unowned ⇒ not flagged, benign
note" behavior, and it is what makes the governing allow-list text
enforceable. It also gives defence in depth on R1-F01: even if D3.1
normalisation regressed, `public.bil_invoices` reaches state 6 and ERRORs
rather than passing. Neither mechanism is relied on alone.

**D3.3 — Resolution precedence is pinned, and conflicts are ERROR.**

1. Part count: a 1-part name resolves by longest matching
   `owned_table_prefixes`. A 2-part `schema.table` resolves per rule 2.
   **A name of 3 or more parts is ERROR** — a cross-database reference is
   outside the ownership model entirely.
2. For a 2-part name: if the schema **equals `default_schema`**, strip it
   and resolve the remainder by prefix (this closes R1-F01(a) — a
   qualified identifier may no longer bypass `owned_table_prefixes`).
   Otherwise resolve by `owned_schemas`.
3. `owned_schemas` must be **disjoint from `default_schema`**, enforced
   at parse time. Without this, a module declaring
   `owned_schemas: ["public"]` would capture every `public.<anything>` as
   state 1 clean — re-opening R1-F01 from the opposite direction.
4. If an identifier's **schema resolves to module A while its prefix
   resolves to module B**, that is **ERROR**, never resolved by iteration
   order.

Rules 3 and 4 exist because Verdict C adjudicated the "unambiguous
attribution of a table to exactly one owner" invariant over a
**one-dimensional** ownership space (prefix versus prefix). This ADR
widens that space with schema ownership and a default schema, so Verdict
C's rule is **carried into the new dimensions**. Leaving it behind would
silently narrow a binding decision's reach.

**D3.4 — Reserved identifiers, checked before ownership resolution.**
`pg_catalog`, `pg_temp`, `information_schema`, and PostgreSQL's reserved
`pg_` identifier prefix are state 4. The reserved check runs **before**
ownership resolution, and `pg_`, `pg_catalog`, `pg_temp` and
`information_schema` are **rejected at parse time** as
`owned_table_prefixes` or `owned_schemas` values. Note that `pg_`
satisfies the D2 prefix floor (confirmed by execution), so without this
rule a module could declare it and make `pg_foo` ambiguous between state
1 and state 4.

**D3.5 — `external_table_references` is a declaration, never an
exemption.** An entry that resolves to **any** module's
`owned_table_prefixes` or `owned_schemas` is **ERROR**
`MODULE_DEPS_GATE_INPUT_INVALID` at parse time. Entries may only name
identifiers that no module owns. Every declared entry is disclosed **by
name**, with a count, in both text and `--json` output on every run
**including PASS**.

Without that constraint the field would be a manifest-layer allowlist
over the gate's headline invariant — a module could declare another
module's table and take state 5's clean outcome. That would contradict
the tool's own contract ("Neither flag offers a skip, exempt, or
allowlist path"), `GOV-01-R04`'s no-bypass requirement, and §24.1's "may
reference **only** their owned table prefix/schema and approved …
interfaces". ADR-009 D5 rejected the same shape for gate 4, and the same
reasoning governs here.

### D4 — Reserved importers: `_shared` and `_root`

Both are **domain-free**: they own no prefixes, no schemas, and no
interfaces, and neither may be declared in the manifest. The guard is a
reserved **set** `{"_shared", "_root"}`, not the single `_shared` check
that exists today — `_root` fully matches the module-name identifier
regex (confirmed by execution), so without this a manifest could declare
a module named `_root` and capture modules-root files.

- **`_shared`** keeps its current semantics, which round 1 verified
  correct against `.claude/rules/backend/architecture.md` control 3: a
  domain module may import `_shared`; `_shared` importing a domain
  module's internals or referencing its owned table is a violation. (The
  tool docstring states this rule backwards and must be corrected —
  R1-F16; the code is right.)
- **`_root`** is the importer for files directly under `--modules-dir`.
  Those files are **scanned, not refused**: they are fully inspectable,
  and `backend/app/modules/conftest.py` exists in the real tree today, so
  skipping them is a real coverage hole (R1-F03). Imports of another
  module's declared `public_interfaces` are allowed; imports of another
  module's internals are `CROSS_DOMAIN_SQL_IMPORT`; the §6.3 pair check
  is inapplicable (no domain); and because `_root` owns nothing, **every
  attributed table reference from a modules-root file is state 2 (FAIL)
  and every unattributed one is state 6 (ERROR)**.

  **Disclosed consequence, so it is never misread as a regression:** a
  root file that references any owned table is a permanent **FAIL**, not
  an ERROR. That is the outcome §24.1 requires — a file owning nothing
  may reference nothing — but it must be stated plainly rather than
  justified as avoiding a "permanent ERROR for a legitimate file", which
  it does not do.

### D5 — Coverage: totality is a reconciliation, relative to the supplied root

1. A **second, independent enumeration** from the `--modules-dir` root is
   reconciled against the union of the per-module walks. Every path must
   land in **exactly one** bucket: discovered-module descendant,
   `_shared` descendant, modules-root file, inert, pruned-and-counted, or
   **unattributed ⇒ ERROR `MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH`**. A
   reconciliation rather than a single traversal is the point: a
   discovery bug becomes an ERROR instead of a silent omission.
2. A non-discovered directory under `--modules-dir` containing any
   non-inert file is that ERROR. Since PEP 420 makes it an importable
   package claiming no declared ownership, it is the same condition the
   contract already treats as ERROR for a discovered module with no
   manifest entry (closes R1-F04).
3. **The reconciliation enumeration does not follow symlinks** and
   buckets each as refused ⇒ ERROR, identically to the per-module walk.
   Otherwise reconciliation could enumerate outside the fixture root and
   regress the fixture-containment property round 1 verified.
4. **No `Path.exists()`, `Path.is_dir()`, or `Path.is_file()` may gate
   *whether* a scan happens.** They return `False` on `EACCES` and
   reproduce the exact fail-open shape that is the live NON_CONVERGING
   item on the migration-ordering surface (SCN-070). Enumeration must
   surface `OSError` explicitly through D7. Existing `is_symlink()` and
   `is_dir()` **refusal** checks stay — they fail closed in the right
   direction; the prohibition is on using them to decide to skip.
5. All bucket counts appear in the report, so a PASS is self-evidencing.
6. **Totality is relative to the supplied `--modules-dir`.** It asserts
   nothing about a wrong root, and a manifest-declared-but-absent module
   remains a note, not an ERROR. Both facts belong in the coverage note.

### D6 — SQL trigger and the zero-table statement class

1. The statement-verb set is a **broad trigger over-approximation**, not
   a detector allow-list: `SELECT INSERT UPDATE DELETE TRUNCATE MERGE
   COPY WITH CREATE ALTER DROP GRANT REVOKE LOCK CALL EXECUTE REFRESH
   REINDEX VACUUM ANALYZE COMMENT`. Because a broader trigger can only
   ever yield strictly more ERRORs, it may be widened freely in future
   rounds without weakening the gate. This is what ends the regex
   treadmill (closes R1-F02).
2. Both `str` and `bytes` literals are in scope; `bytes` decode is UTF-8
   then latin-1, and a decode failure is ERROR via D7 (closes R1-F11).
3. **The I-1 backstop, corrected.** A triggered statement that yields
   **zero** extracted table-position identifiers is **ERROR** if and only
   if it also contains at least one table-position keyword (`FROM JOIN
   INTO UPDATE TABLE ONLY REFERENCES`) or a bare-table verb form
   (`TRUNCATE`, `COPY`, `LOCK TABLE`, `DROP TABLE`, `ALTER TABLE`,
   `CREATE TABLE`, `GRANT … ON`). A triggered statement with **no table
   position at all** — `SELECT 1`, `SELECT now()`, `ANALYZE`, a bare
   `VACUUM` — is **clean, counted, and disclosed under its own counter**.
   An unqualified "triggered but zero refs ⇒ ERROR" rule would ERROR on
   the most common operational SQL in existence, which generates exactly
   the pressure to weaken the gate that the docstring-prose exclusion
   below exists to avoid. The dangling-keyword shape stays ERROR, so the
   fail-closed property is unchanged.
4. **Docstring positions** (module, class, and function `body[0]` `Expr`
   `Constant`) are excluded from SQL scanning, counted, and disclosed. A
   false `CROSS_DOMAIN_SQL_IMPORT` on English prose (R1-F10) is worse
   than the residual. **The residual is disclosed as a residual:** SQL
   held in a docstring and reached via `SomeClass.__doc__` needs no
   `exec`, `eval`, or `compile`, so it is **not** covered by the
   dynamic-construct rule and must be named in the coverage note.
5. The analyser **never** imports, `exec`s, `eval`s, or `compile`s any
   file under `--modules-dir`. `ast.parse` does not execute code and it
   must stay that way. A dynamic import can therefore only ever be
   answered with ERROR, never resolved by running it.
6. **`BIDIRECTIONAL_PAIRS` stays pinned in source and is never
   manifest-configurable**, because §6.3 is normative. §6.3's rejection
   of "direct repository/table coupling" on the reverse edge is carried
   by `CROSS_DOMAIN_SQL_IMPORT` taking precedence over the pair check, as
   round 1 verified.

### D7 — Error taxonomy: total, disjoint, and never exit 0

| Code | Severity | Exit | Condition |
|---|---|---|---|
| `CROSS_DOMAIN_SQL_IMPORT` | FAIL | 1 | D3.2 state 2, or a cross-domain internal import |
| `REVERSE_EDGE_NOT_EVENT_DRIVEN` | FAIL | 1 | A §6.3 reverse synchronous edge |
| `MODULE_DEPS_TABLE_UNATTRIBUTED` | ERROR | 2 | D3.2 state 6 |
| `MODULE_DEPS_SOURCE_UNINSPECTABLE` | ERROR | 2 | Reduction to statements/tokens failed or was impossible |
| `MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH` | ERROR | 2 | D5.1 unattributed bucket |
| `MODULE_DEPS_GATE_INPUT_INVALID` | ERROR | 2 | Manifest or CLI-input violation of D1-D4 |
| `MODULE_DEPS_GATE_INTERNAL_ERROR` | ERROR | 2 | D7.3's outermost funnel |
| `MODULE_DEPS_GATE_VACUOUS` | INCONCLUSIVE | 2 | No substantive file exists |

**D7.1 — `UNINSPECTABLE` and `TABLE_UNATTRIBUTED` are disjoint, and the
discriminator is stated.** `MODULE_DEPS_SOURCE_UNINSPECTABLE` applies iff
reduction to statements/tokens **failed or was impossible** — runtime
assembly, a dynamic construct, a node-level decode failure, a dangling
keyword, unlexable text. `MODULE_DEPS_TABLE_UNATTRIBUTED` applies iff
lexing **succeeded** and produced at least one table-position identifier
resolving to none of states 1-5. The discriminator is whether an
identifier was actually extracted. Without this rule the two codes
overlap, and an acceptance corpus cannot assert an exact expected code on
precisely the rows where precision matters most.

**D7.2 — Violations and uninspectable findings are reported partitioned,
never collapsed.** The run stays ERROR with exit 2 when anything is
uninspectable, but the report carries **both** lists. Returning only the
uninspectable list discards real violations and hands a module a lever to
hide them behind one f-string (R1-F09).

**D7.3 — No exit path exists for "non-zero with no report".** Every read
and decode goes through one helper converting `OSError`,
`UnicodeDecodeError`, and `ValueError` into the gate's input-error type
(the convention `_load_json` and the RLS gate's catalog read already
use), and `main` gains an outermost funnel mapping any unexpected
exception — current or future — to `MODULE_DEPS_GATE_INTERNAL_ERROR` at
exit 2. **The funnel's emission is a minimal last-resort path** (a
literal text line, plus a hand-built minimal JSON object under `--json`)
that does **not** call back into the report builder; otherwise a throw
during report rendering reproduces R1-F07's "exit 1, empty stdout" one
layer up. The funnel must not catch `SystemExit` or `KeyboardInterrupt`,
and must never produce PASS. This closes R1-F07 by construction rather
than at the single observed throw site.

**D7.4 — Violations are deduplicated and deterministically ordered** by
`(code, subject, detail)`, first-seen order preserved within a key
(R1-F15, R1-F20).

### D8 — Report surface: a PASS must be self-evidencing

Every run, **including PASS**, discloses in both text and `--json`:
declared / discovered / scanned module counts; files inspected, inert,
pruned by reason, and at the modules-root; all D5.1 bucket counts;
docstrings excluded from SQL scanning; SQL-trigger strings inspected;
zero-table triggered statements (D6.3); table references by D3.2 state
(own / other / CTE / system / declared external), with declared external
references listed **by name**; cross-module import edges resolved and
approved; and a coverage note naming what is **not** examined — out-of-tree
SQL, ORM-reflected and driver-level dynamic SQL, non-Python/non-`.sql`
sources, docstring contents and the `__doc__` residual (D6.4), the
residual undecidability of Python dynamic dispatch, the lexer's SQL
dialect limitation, the relativity of coverage totality to the supplied
root (D5.6), and that **gate 2 is not a security boundary**.

**Gate 2 is architecture hygiene, not a security boundary.** Anyone with
commit rights can defeat any static lint. The security boundary for
tenant and domain isolation is gate 1 (RLS) plus database grants,
enforced at runtime by the engine. This must be on the face of the
report, not buried — it is what makes ERROR-on-unknown an acceptable bias
rather than a false claim of completeness.

### D9 — Explicitly rejected, because each is a silent bypass or an owner-reserved change

- **Any skip flag, exempt list, path-pattern allowlist, or
  per-module/per-file suppression** for gate 2. This is the bypass the
  gate exists to prevent and `GOV-01-R04` forbids it.
- **An unconstrained `external_table_references`** (i.e. without D3.5).
  It is the same bypass wearing a schema field's clothing.
- **Making `BIDIRECTIONAL_PAIRS` manifest-configurable.** §6.3 is
  normative; this would be a TSD change.
- **"Unowned ⇒ benign note"**, in any form. It is the fourth, undocumented
  terminal state that produced R1-F01 and it contradicts §24.1's
  allow-list wording.
- **Resolving a dynamic import by importing or executing the file.**
- **Committing `contracts/modules/ownership.json`** with real domain and
  prefix bindings for the six scaffolds: **owner-reserved** (material
  architecture change), and per DC-09 it also requires its own ADR. Not
  authorised here and not a dependency of anything here.
- **Adding a third-party SQL parser** (`sqlglot`, `pglast`, `sqlparse`)
  in this contract. It is a capability requiring the full
  `CAPABILITY_POLICY.md` lifecycle and a registry row (CAP-008 is the
  precedent for the cost; BUG-038 is the precedent for skipping it), plus
  a decision on where `tools/` dependencies live. Deferred, with the
  dialect limitation disclosed per D8, and re-opened by the trigger in
  "Follow-up".

## Alternatives considered

| Alternative | Consequence | Verdict |
|---|---|---|
| Widen `_SQL_DML_RE`, the dynamic-import name list, and the uninspectable shape list | Moves all 21 round-1 shapes without removing any cause; a closed deny-list over an open input space is an allow-list by default. This is the failure mode SCN-070's convergence assessment already recorded on another surface | **Rejected** — the polarity inversion in D3.2/D6.3 is the fix |
| Adopt a third-party SQL parser now | Gates four Blocker scenarios behind a capability qualification rather than behind engineering, for a lint that currently analyses only synthetic fixture SQL; and it would not change the fail-closed property, only reduce false ERRORs | Rejected for now; see D9 and Follow-up |
| Refuse modules-root files as uninspectable | ERROR is for the uninspectable, not the unexamined; `conftest.py` is fully inspectable and exists in the real tree today | Rejected — D4's `_root` importer scans them |
| Treat state 6 (unattributed identifier) as a FAIL rather than an ERROR | §24.1's allow-list wording would support it, and both are non-zero. But the gate cannot distinguish "another module's table" from "a table nobody owns", so a FAIL would have to name an owner it does not know | Rejected — ERROR is the honest classification; both fail CI, which is what the governing text requires |
| Promote zero-subject runs to INCONCLUSIVE in the tool | Invents a new real-tree failure mode on a tree that has not been modelled | Rejected; addressed by D8's counters plus an evidence-set obligation. **This closes R1-F12(i) by relocation, not elimination, and must be labeled as such** |
| Reject module names that are string prefixes of one another | Rejects a legal configuration round 1 verified as correctly attributed (`pos` vs `pos_extra`) | Rejected; D2's identifier validation alone closes R1-F08 |
| Bump the manifest to `version: 2` | Implies a migration obligation for consumers that do not exist | Rejected; D1.2 keeps version 1 |

## Consequences

- **The gate rejects and ERRORs on strictly more input than before.** New
  ERROR surfaces: an unattributed table identifier; a ≥3-part identifier;
  any `__init__.py`-less directory containing a non-inert file under
  `--modules-dir`; any `exec`/`eval`/`compile` in a scanned file; a
  schema-owner/prefix-owner conflict; and legitimate-but-unusual SQL the
  lexer cannot reduce. These are **additional fail-closed paths, not new
  defects**.
- **A hypothetical real-tree run gains those ERRORs on top of the
  existing missing-manifest ERROR.** The real tree is already ERROR by
  design and asserts nothing about ownership. Additionally, per D4, a
  modules-root file referencing any owned table would be a **FAIL**. All
  of this must be disclosed in implementation records so it is never read
  as a regression.
- **Existing fixtures may need re-expression.** The D2 prefix floor
  rejects one-character-plus-underscore prefixes, so any fixture using
  `a_` — including the one round 1's P0 reproducer used — must adopt a
  conforming prefix, or it will assert `GATE_INPUT_INVALID` where it
  means to assert `FAIL`.
- **Residual risk, disclosed.** This contract proves properties of
  *statically analysable source under one supplied root*. It does not
  prove anything about SQL reaching the database from outside that tree,
  ORM reflection, driver-level dynamic SQL, a native extension, or
  base64/`eval`-obfuscated text. It is not a security boundary (D8). Any
  PASS must be worded "every inspected subject under the supplied
  modules-dir", never "the application has no cross-domain coupling".
- **No scenario is promoted by this ADR.** SCN-MOD001-006/-007/-095/-096
  remain NOT EXECUTED and unpromoted, and the round-1 **BLOCKED** verdict
  stands until a fresh independent round-2 review says otherwise.

## Conformance determination

Conforms to Blueprint > TSD v1.4.1 > design bundle > EIP v1.4.1. It
changes:

- **no TSD scope** — it implements §24.1's own gate-2 obligation and
  §6.3's normative directed graph, both read first-hand from the
  governing docx this session;
- **no domain model** — no real directory is bound to any domain code,
  table prefix, or schema, and `contracts/modules/ownership.json` is
  neither authored nor made authorable (D9);
- **no product, pricing, or business decision** — a CI lint's input
  schema is none of these;
- **no module scope** — `GOV-01-R04` already requires this gate;
- **no routing** — ADR-005 is unchanged; implementation routes to
  `veyro-implementer` (Sonnet) per the existing mapping, and any
  rerouting would be an ADR-005 amendment, not a silent change;
- **no capability** — stdlib only; no third-party parser is adopted (D9).

It incurs **no spend**, uses **no real member data**, touches **no
production**, and asserts **no material architecture change**. Per
Verdict B's split, **no owner approval is required.** The items in D9
that would require it are each explicitly rejected and none is adopted.

The one owner-reserved item on this surface — binding the six
`backend/app/modules/` scaffolds to domain codes and owned table prefixes
— remains **`BLOCKED: OWNER_APPROVAL_REQUIRED`** and is untouched by this
ADR.

## Follow-up

**For the gate-2 implementer (`veyro-implementer`, Sonnet, dispatch D1a
then D1b):** implement to D1-D8 literally. The adjudication record
`GATE2-R1-QUALIFIED-LEAD-DECISION-2026-10-05.md` §3 carries the full
correction list this ADR encodes; where that record and this ADR differ
in wording, **this ADR governs** on schema and semantics. Two round-1
misreads must be corrected rather than carried forward: do **not**
restate "the 12 `E501`" (round 1 measured 299 at ruff's default
88-column width and showed the figure is config-dependent — pin a root
`ruff.toml`, re-run, and record the figure measured under the pinned
config), and do **not** claim the docstring `__doc__` residual is covered
by the dynamic-construct rule (D6.4). Label R1-F12(i) a relocation, not a
closure.

**For the acceptance corpora:** every row asserts an **exact outcome
code**, not merely a non-zero exit — D7.1 is what makes that possible.
Each corpus row must read its own fixture back to prove the intended
construct is present, and each corpus must include the control row that
produces the expected denial. The manifest corpus must cover, at
minimum: `owned_table_prefixes` of `["a"]`, `["ab"]`, `["a_"]`, `["ab_"]`
(reject, reject, reject, accept); `owned_schemas: ["public"]` against
`default_schema: "public"` (reject); a schema-owner/prefix-owner conflict
(ERROR); an `external_table_references` entry naming another module's
owned table (reject); a module declared as `_root` (reject); a
non-existent `public_interfaces` entry (reject); and **re-assertion of
Verdict C's three cases unchanged** — same-module nesting accept,
cross-module overlap ERROR, exact duplicate ERROR.

**For the mutation controls:** the mutation set must attack the **new
clean states**, not only the closed fail-opens. At minimum, each of these
must be killed by a named test: state 4's reserved check widened from the
`pg_` prefix to any `pg`-initial identifier; state 5 accepting an
external reference that names another module's owned table; state 3's CTE
collection widened to accept any bare identifier as locally bound;
`_root` given ownership so modules-root violations read clean; and a
report counter hardcoded non-zero. A surviving mutant is a **blocker for
the dispatch**, not a note.

**For the independent round-2 reviewer (`veyro-code-reviewer`, Opus,
fresh context):** verify the implementation against D1-D8 literally.
Specifically try to (a) get a cross-domain table reference to PASS by any
identifier spelling, qualification, or case; (b) get a file scanned out
of existence by location, package shape, or symlink; (c) get a non-zero
exit with no report or invalid `--json`; (d) use
`external_table_references`, `default_schema`, or `owned_schemas` as a
bypass; and (e) make the two ERROR codes in D7.1 overlap. Judge whether
this ADR itself has a gap — if so, report it as a finding against
ADR-011, which `veyro-lead` amends. This ADR is an **input** to that
review, never an approval (DC-14).

**Not decided here; flagged for their owners:**

- **Third-party SQL parser (CAP-009 candidate).** Re-open when real-tree
  gate-2 activation is unblocked, or when fixture SQL complexity makes
  ERROR-by-default untenable. Requires the full `CAPABILITY_POLICY.md`
  lifecycle plus a decision on where `tools/` dependencies live. The
  `_extract_table_refs(text) -> TableRefs | Uninspectable` seam exists so
  that only one function is replaced and the acceptance corpora are the
  unchanged acceptance test for the replacement.
- **CI wiring.** No `.github/workflows/` and no committed CI config exist
  (round 1 confirmed independently), so Verdict A.4's premise is moot
  today. When CI is first wired, the two legal resolutions are to pin the
  step to a fixture tree with explicit flags and label it fixture-scoped,
  or to hold the step unwired with the gap disclosed. **Inventing a
  skip/exempt path remains forbidden.**
- **Whether the evasion corpora need their own scenario rows** or are
  code-assurance evidence under SCN-MOD001-007. Catalog design belongs to
  `veyro-scenario-reviewer`; non-binding recommendation is no new rows.
- **Real-tree domain ownership** — owner-reserved, unchanged, not a
  dependency of this ADR.
- **Governance records.** `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, the
  scenario catalog, and the evidence index were deliberately **not**
  edited by this session. The orchestrator should reference ADR-011 in
  them when next reconciling.

---

# Addendum 2026-10-06 — D6.7: extraction totality

**Status:** DECIDED 2026-10-06. Conforming to the governing baseline; **no owner
approval required** (see "Addendum conformance" below).
**Decided by:** `veyro-lead` (registered architecture/ADR-decision role, fresh bounded
adjudication dispatch; `claude-opus-5[1m]` — Opus 5 (1M context), as reported by this
environment). Not the gate-2 implementer, not the round-1 or round-2 reviewer. No code,
security, or scenario review approval is given or implied.
**Model attestation:** NONE RUN BY THIS SESSION. `mr_verify.py` was not run against this
dispatch's own transcript — self-attestation is of little value and the tool is the
orchestrating session's to run. Stated rather than omitted.
**Authority:** this ADR's own Follow-up, which directs the round-2 reviewer to "judge
whether this ADR itself has a gap — if so, report it as a finding against ADR-011, **which
`veyro-lead` amends**." That finding is **R2-N02**, in
`knowledge/03-Modules/MOD-001/evidence/code-review/GATE2-MODULE-DEPS-CODE-REVIEW-ROUND2-2026-10-06.md`.
**Adjudication record (reasoning, causal chain, alternatives rejected, acceptance criteria,
scope boundaries):**
`knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R2-N01-N02-QUALIFIED-ROOT-CAUSE-2026-10-06.md`.

**Nothing above this line is modified.** The original decision text of D1–D9, the
Alternatives, Consequences, Conformance determination, and Follow-up sections is preserved
byte-unchanged as the historical record. This addendum **adds** one clause (D6.7), amends
**D7.1** by reference, and **corrects one false disclosure sentence** required by D8.

## Why this addendum exists

Round-2 independent code review (**BLOCKED**, P0=1/P1=1/P2=2/P3=2) found that an
implementation can satisfy D1–D8 **literally** and still let a cross-domain raw-table
reference reach **PASS, exit 0** — reproduced independently by the adjudicating session on
its own synthetic fixture, with the D8 report simultaneously asserting "the counts are
complete for this run."

The cause is a layer this ADR never constrained. Gate 2's SQL path has three layers: the
**trigger** (governed by D6.1), **extraction** (text → the multiset of table-position
identifiers — **governed by nothing**), and **attribution plus backstop** (governed by D3.2,
D6.3, D7.1). D3.2's opening sentence — "Every identifier in a table position resolves to
exactly one of six states" — and D8's self-evidencing requirement both *presuppose*
extraction totality that this ADR never mandated, while D7.1 treats extraction as a given
primitive ("the discriminator is whether an identifier was actually extracted").

D6.1 argued correctly that widening the **trigger** "can only ever yield strictly more
ERRORs." That monotonicity does **not** transfer to extraction, and the original decision did
not notice the polarity flip. Because the D6.3 backstop is scoped to the **statement**
(`if not idents:`), the first identifier that extracts cleanly **disarms** the refusal that
would otherwise have covered the whole statement:

> **In the original design, extracting one identifier is strictly less safe than extracting
> none.**

Consequence, confirmed by execution against source `b9e012a4…`: a comma-separated `FROM`
list, a `REFERENCES` clause, and a `USING` clause each PASS at exit 0, and the defect defeats
**both** D3.2 state 2 (`CROSS_DOMAIN_SQL_IMPORT`) **and** D3.2 state 6
(`MODULE_DEPS_TABLE_UNATTRIBUTED`) — i.e. the whole polarity inversion D3.2 was written to
achieve. That is the effect **D9** prohibits "in any form," in a form more harmful than the
one D9 named: not a benign note, but no note plus a false completeness claim. Separately,
`_TABLE_POSITION_KEYWORDS` omits **`USING`**, so that position is invisible to the backstop
as well — proving vocabulary breadth cannot be the fail-closed mechanism.

## D6.7 — Extraction is an over-approximation, and partiality fails closed

**D6.7.1 — Monotone-bias rule.** The extractor must be an **over**-approximation of the true
table-position set, for the mirror of D6.1's reason: an over-extracted identifier reaches
state 6 and ERRORs (loud, bounded, correctable), while an under-extracted one reaches no
state at all and is silently clean. Where the lexer must guess, it guesses toward extracting.
**Narrowing the extractor is therefore never a free optimisation** and requires its own
recorded decision.

**D6.7.2 — Per-position fail-closed rule.** The D6.3 I-1 backstop and the dangling-keyword
refusal are evaluated **per table position**, never per statement. A triggered statement in
which **any** recognised table-position signal did not yield an identifier carried to D3.2
attribution is **ERROR `MODULE_DEPS_SOURCE_UNINSPECTABLE`** naming that signal, **regardless
of how many other identifiers extracted cleanly.** The `if not idents:` guard is replaced by
an accounting comparison between recognised signals and attributed identifiers. The invariant
to implement and test against:

> For any statement text T, the gate's outcome must be **no weaker** — on the ordering
> `clean < FAIL/ERROR` — than the outcome it would produce for T if the extractor had
> returned nothing. **Partial extraction may never be safer than total extraction failure.**

**D6.7.3 — List positions.** A table-position keyword introducing a list (`FROM`, `JOIN`,
`INTO`, `USING`, `REFERENCES`, `ONLY`, and the bare-verb forms) extends across commas at the
same parenthesis depth until a clause boundary or statement end. **Every element is its own
table position** and is individually subject to D6.7.2. An element the lexer cannot reduce to
an identifier is ERROR, never dropped. Where the clause boundary is itself uncertain, the
walk **continues** rather than stopping (per D6.7.1) — an over-extracted column name ERRORs
at state 6, which is the safe direction.

**D6.7.4 — Vocabulary is a floor, not the mechanism.** `_TABLE_POSITION_KEYWORDS` must remain
a superset of the extractor's keyword set and must additionally include **`USING`**.
Vocabulary completeness is a floor that lowers the ERROR rate; it is **not** the fail-closed
mechanism, and no clause of this ADR may be read as making the gate's soundness depend on it.
A keyword added to one set widens both at once — the existing `_implies_table_position` seam
exists for exactly that and must be preserved.

**D6.7.5 — D8 truthfulness (correcting a live false claim).** "the counts are complete for
this run" may **not** be asserted for the table-reference attribution dimension unless the
run established that D6.7.2's accounting held for every subject. Otherwise the figure is
disclosed as a **lower bound**, in the same terms D7.2 already requires for the FAIL
partition. The current unconditional sentence is affirmatively false and must be removed or
conditioned. A false completeness claim is worse than a disclosed limit: it is the sentence a
reader relies on when judging whether a PASS means anything.

**D6.7.6 — D7.1 amended by reference.** D7.1's discriminator is well-founded only under
D6.7.1–.3. It now reads: *whether every recognised table position yielded an identifier.* A
silently-unextracted position is `MODULE_DEPS_SOURCE_UNINSPECTABLE`, never invisible. D7.1's
disjointness with `MODULE_DEPS_TABLE_UNATTRIBUTED` is unchanged and still holds.

**D6.7.7 — Explicit non-expansion.** D6.7 authorizes nothing beyond the above. It does **not**
authorize a third-party SQL parser (**D9**'s deferral stands); does **not** touch D3.2 state
3, `cte_names`, the live call site, the `cte_names` default, or any resolution order (the
U1/U2 **B HOLD**,
`evidence/implementation/GATE2-R1-D6-U1-U2-QUALIFIED-REDECISION-2026-10-05.md`, continues in
force and governs that lane, including its exhaustive §4 prohibition list and its
non-negotiable four-item re-opening bar); does **not** touch real-tree domain ownership
(owner-reserved, unchanged, not a dependency); and adds **no** skip, exempt, allowlist, or
suppression path of any kind. **D3.3/D3.4's silence on state 3's position in the precedence
order is NOT resolved by this addendum** — it remains logged, not decided.

## Alternatives rejected for this addendum

| Alternative | Consequence | Verdict |
|---|---|---|
| Widen `_TABLE_KEYWORD_RE` only | Moves the observed instances without touching the class; the partial-extraction-disarms-backstop asymmetry survives and the next unlisted keyword reproduces the P0. The treadmill this ADR's own Alternatives table already rejected once | **Rejected** |
| Position-scope the backstop, vocabulary unchanged | Necessary but not sufficient: a position introduced by a keyword in no list (`USING`) is invisible to a position-scoped backstop too | **Rejected as the whole fix; adopted as D6.7.2, one part of four** |
| Keep statement scope, ERROR when `len(idents) < len(signals)` | The same defect at a different threshold — still reasons over the statement aggregate | **Rejected** |
| Full residue accounting (classify every identifier-shaped token; unclassified ⇒ ERROR) | Structurally the strongest shape and the long-term target, but it *is* parsing — it needs the D9-deferred parser capability, and would ERROR on ordinary SQL at a rate that generates exactly the pressure to weaken the gate that D6.3's own correction exists to avoid | **Rejected for now**; re-open with the D9 parser trigger |
| Treat an unaccounted position as FAIL rather than ERROR | Same reasoning as D3.2's existing state-6 row: the gate cannot name an owner it does not know | **Rejected** — ERROR, exit 2; both fail CI, which is what §24.1 requires |
| Disclose it as a residual under D8 and proceed | D8 can honestly describe a false-*fail*; it cannot discharge a false-*clean*. A formally D8-compliant, substantively misleading report is the outcome to avoid | **Rejected** |
| Defer until a real-tree manifest exists | SCN-MOD001-007 is Blocker-tier and fixture-scoped; its denial must be reliable on fixtures now, and round 2 established it is not | **Rejected** |
| Narrow D6.1's trigger to offset D6.7's higher ERROR rate | Trades a loud refusal for a silent skip — the exchange D6.1 was written to forbid | **Rejected**, and forbidden to the implementer |

## Addendum conformance determination

Conforms to Blueprint > TSD v1.4.1 > design bundle > EIP v1.4.1. D6.7 changes **no TSD
scope** (it moves the implementation *toward* §24.1's allow-list wording and §6.3's rejection
of "direct repository/table coupling" — a foreign key to another module's table is §6.3's
textbook instance and currently PASSes); **no domain model** (no directory bound to any
domain, prefix, or schema; no manifest authored or made authorable — this ADR's scope limit
is inherited verbatim); **no product, pricing, or business decision**; **no module scope**
(GOV-01-R04 already requires a deliberate-violation fail-closed proof for this gate — D6.7 is
what makes gate 2's proof real); **no routing** (ADR-005 unchanged; implementation remains
`veyro-implementer`/Sonnet, so DC-17's routing-change sub-clause is not triggered); and **no
capability** (stdlib-only lexical work — signal counting, comma-continuation at parenthesis
depth and an accounting comparison are all lexically decidable, and the parser-requiring
alternative was identified and rejected above, so D9's deferral stands).

Every D6.7 clause **adds** ERROR surface and removes none, so it is impossible for D6.7 to
weaken any gate. It incurs **no spend**, uses **no real member data**, touches **no
production**, and asserts **no material architecture change**. **No owner approval is
required.**

The one owner-reserved item on this surface — binding the six `backend/app/modules/`
scaffolds to domain codes and owned table prefixes — remains **`BLOCKED:
OWNER_APPROVAL_REQUIRED`**, is untouched, and is not a dependency of this addendum.

## Addendum follow-up

**For the gate-2 implementer (`veyro-implementer`, Sonnet):** implement D6.7.1–.7 literally.
The bounded negative corpus (10 rows, exact outcome codes, each asserted as both a `.py`
literal and a `.sql` file), the non-vacuity positive controls (5 rows — in particular
`SELECT a FROM mem_roster, mem_events` must stay **PASS**, and `SELECT a FROM mem_x JOIN
mem_y USING (id)` must stay **PASS** since `USING (col)` in a join condition is a column list,
not a table position), the seven mutation controls **M-E1…M-E7**, the evidence obligations,
and the explicit scope boundaries are all specified in
`knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R2-N01-N02-QUALIFIED-ROOT-CAUSE-2026-10-06.md`
§5. A surviving mutant is a **blocker for the dispatch**, not a note. The module docstring
paragraph at `tools/validate_architecture_gates.py:249-257` — which documents as current
behaviour the exact "unowned ⇒ not flagged, only counted and disclosed in a note" terminal
state **D9** forbids — must be corrected before any D6.7 remediation record may claim this
work is finished (DC-12).

**For the independent round-3 reviewer (`veyro-code-reviewer`, Opus, fresh context):**
re-execute the eleven-row reproducer in that record's §2 and verify D6.7.2's invariant
directly — try to find any statement in which one cleanly-extracted identifier still
suppresses a refusal elsewhere in the same statement. This addendum is an **input** to that
review, never an approval of it (**DC-14**).

**No scenario is promoted by this addendum.** SCN-MOD001-006/-007/-095/-096 remain **NOT
EXECUTED** and unpromoted, the round-2 **BLOCKED** verdict stands, MOD-001 remains
uncertified, WIP=1 holds and MOD-002 stays locked.

---

# Addendum 2026-10-06 — D6.8: bounded privilege-list narrowing of the table-position signal stream

**Status:** DECIDED 2026-10-06. Conforming to the governing baseline; **no owner approval
required** (see "Addendum conformance determination" below).
**Decided by:** `veyro-lead` (registered architecture/ADR-decision role, fresh decision-only
bounded dispatch; `claude-opus-5[1m]` — Opus 5 (1M context), as reported by this
environment). **Not** the gate-2 implementer, **not** the round-1 reviewer, **not** the
round-2 reviewer. No code, security, or scenario review approval is given or implied, and no
review counter is advanced.
**Model attestation:** NONE RUN BY THIS SESSION. `mr_verify.py` was not run against this
dispatch's own transcript — self-attestation of model identity is of little value and the
tool is the orchestrating session's to run against the actual transcript. Stated rather than
omitted.
**Authority:** **D6.7.1**, verbatim: *"**Narrowing the extractor is therefore never a free
optimisation** and requires its own recorded decision."* This addendum is that recorded
decision. The amending power is this ADR's own `## Follow-up`, which directs that a gap in
this ADR be *"report[ed] as a finding against ADR-011, **which `veyro-lead` amends**"* — the
same authority under which the D6.7 addendum was recorded, acting on round-2 finding
**R2-N01** (P0) and its root-cause qualification.
**Decision evidence (reasoning, probes, alternatives, acceptance criteria, scope
boundaries):**
`knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R2-N01-D68-PRIVILEGE-NARROWING-QUALIFIED-DECISION-2026-10-06.md`.
**Root-cause record this addendum discharges:**
`knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R2-N01-D67-REMAINING-SIGNAL-ROOT-CAUSE-2026-10-06.md`
§6.1 half (2), §6.3's reservation of this adjudication to `veyro-lead`.

**Nothing above this line is modified.** The original decision text of D1–D9, the
Alternatives, Consequences, Conformance determination and Follow-up sections, **and the
entire 2026-10-06 D6.7 addendum (D6.7.1–D6.7.7, its Alternatives table, its conformance
determination and its follow-up), are preserved byte-unchanged** as the historical record.
This addendum **adds** one clause (D6.8). It amends no earlier clause, and it narrows none
of D6.7's obligations.

## Why this addendum exists

The causal chain, in order:

1. **D6.7.1 made extraction a deliberate over-approximation.** Where the lexer must guess,
   it guesses toward extracting, because an over-extracted identifier reaches D3.2 state 6
   and ERRORs — loud, bounded, correctable — while an under-extracted one is silently clean.
2. **One consequence of that bias is a lexical collision in the *safe* direction.**
   `UPDATE` and `REFERENCES` are PostgreSQL **privilege names** as well as recognised
   table-position signal keywords. In `GRANT UPDATE ON mem_roster TO r` the privilege word
   `UPDATE` is read as a table-position signal whose target is the following token — the
   reserved word `ON`. The statement therefore carries a spurious position resolving to the
   identifier `on`, which no module owns.
3. **That over-extraction cannot admit a clean pass, but it still defeats three things this
   ADR requires.** Measured gate rows (root-cause record §4.2): **2A** `GRANT UPDATE ON
   mem_roster TO r` and **2B** `GRANT REFERENCES ON mem_roster TO r` are ERROR exit 2
   naming a table nobody wrote, i.e. a wholly own-domain legitimate grant is refused;
   **2C** `GRANT UPDATE ON bil_invoices TO r` emits the correct `CROSS_DOMAIN_SQL_IMPORT`
   but carries ERROR status, so the denial is mislabelled at status level against
   SCN-MOD001-007's requirement that the denial name the right thing; **2D** `GRANT SELECT,
   INSERT, UPDATE ON mem_a, bil_invoices TO r` prints `CROSS_DOMAIN_SQL_IMPORT` **twice**
   and D8 reports **4** table references where **2** exist, because the privilege word is
   also a `_LIST_POSITION_SIGNALS` member and walks the object comma list a second time.
   Rows 2A–2D are therefore D3.2 state-precision and **D6.7.5** count-truthfulness defects.
4. **Critically, the over-extraction was a measured accidental backstop.** Root-cause record
   §5: the text `REVOKE SELECT ON mem_roster`⏎`SELECT a FROM bil_invoices` reached **PASS
   exit 0** (a demonstrated false clean), while the same text spelled `REVOKE UPDATE …`
   reached ERROR exit 2 — and did so **only** because the spurious `UPDATE -> ON` position
   raised state 6. Closing the collision first would have removed that backstop and
   **widened** the demonstrated false-PASS surface while every test stayed green. **This is
   why D6.8 is not a free optimisation and why its ordering is normative (D6.8.6).**
5. **The ordering precondition is now satisfied.** Half (1) — replacing
   `_revoke_grantee_exclusion_offset`'s unbounded `.search` with a positively-computed,
   anchored walk — landed in source `8cb5790a…`
   (`GATE2-R2-N01-D67-REVOKE-FROM-BOUNDED-P0-LOCAL-VERIFICATION-2026-10-06.md`), and this
   session re-verified it directly rather than on that record's word. D6.8 is therefore
   orderable now, and not before.

## D6.8 — Privilege-list signal suppression, bounded, lossless, and retained on uncertainty

**D6.8.1 — What may be suppressed, and nothing else.** Exactly one new suppression is
authorized: a recognised table-position signal whose keyword token is a PostgreSQL
**privilege name** occupying the **privilege-list region** of a `GRANT`/`REVOKE` statement is
not a table position and contributes no position to the D6.7.2 stream.

The suppressible token set is **derived, not hand-listed**: it is the intersection of
(a) the closed PostgreSQL privilege-name vocabulary of **D6.8.2** and (b) the union of the
keyword tokens of every `_TABLE_POSITION_SIGNAL_SOURCES` entry. Today that intersection is
exactly

> **{ `UPDATE`, `REFERENCES`, `TRUNCATE` }**

and the implementation must carry a direct unit assertion pinning the suppressible set
**equal** to that computed intersection, so a future signal keyword that is also a privilege
name is caught by a failing test rather than silently omitted. `TRUNCATE`'s inclusion is
deliberate and measured: `_truncate_table_position_matches` already excludes the adjacent
`GRANT TRUNCATE ON t` shape at its own source, but **not** `GRANT TRUNCATE, SELECT ON t`,
which this session measured as a live spurious unresolved position. No other token is
suppressible for any reason, and the set may not be widened by the implementer.

**The object-clause `ON` is never suppressible, for two independent reasons:** it is outside
the region by D6.8.3's open upper end, and `ON` is not a PostgreSQL privilege name so it is
not in the derived set. Both reasons must hold in the implementation; neither alone is relied
upon.

**D6.8.2 — The privilege-list region, positively computed.** For a `GRANT`/`REVOKE` verb
keyword match `verb`, let `on = _grant_revoke_object_on_match(text, verb)` — the one function
that already identifies this family's object clause, and which both existing consumers
already go through. If `on` is `None`, **there is no region** and this verb contributes no
suppression.

Otherwise the candidate region is the interval

> **`R = [ verb.end() , on.start() )`** — **lower end CLOSED**, **upper end OPEN.**

The open upper end is normative and load-bearing: it places the object `ON` token strictly
**outside** `R`, so the signal that carries the statement's real target can never fall inside
a suppression region.

`R` is **positively computed** — and suppression is permitted within it — **if and only if
all** of the following hold. They are evaluated by a single left-to-right scan of `R`
maintaining a parenthesis depth initialised to 0:

1. `_GRANT_PRIVILEGE_GAP_RE.fullmatch(text, verb.end(), on.start())` succeeds (the existing
   character-class precondition: word characters, whitespace, `,`, `(`, `)`, `"` only).
2. Parentheses are **balanced within `R`**: depth never goes negative, and depth is **0** at
   `on.start()`.
3. **Every identifier-shaped token at depth 0** — each `[A-Za-z_][A-Za-z0-9_]*` run —
   casefolds into the **closed privilege vocabulary**
   `{ALL, ALTER, CONNECT, CREATE, DELETE, EXECUTE, FOR, GRANT, INSERT, MAINTAIN, OPTION,
   PRIVILEGES, REFERENCES, SELECT, SET, SYSTEM, TEMP, TEMPORARY, TRIGGER, TRUNCATE, UPDATE,
   USAGE}`. This vocabulary is a closed list of PostgreSQL privilege names plus the
   `ALL PRIVILEGES` and `GRANT OPTION FOR` modifier words; it is not extensible by the
   implementer and contains no table-position keyword other than the three in D6.8.1's
   derived set.
4. **No `"` character appears at depth 0**, and no numeric-literal or other non-identifier,
   non-separator token appears at depth 0. Content at depth **≥ 1** is a column list by
   grammar and is exempt from checks 3 and 4.

If any of 1–4 fails, `R` is **not** positively computed, it yields **no suppression at all**,
and every signal inside it is **retained** (D6.8.4).

**This vocabulary check is the load-bearing defence, not the interval arithmetic**, and the
implementer must not treat it as a redundant nicety. `_grant_revoke_object_on_match` is
measured to span an *entire unrelated statement* when a subject carries no depth-0 semicolon:
for `GRANT SELECT`⏎`UPDATE bil_invoices SET x FROM mem_a JOIN mem_b ON mem_q` the candidate
interval covers the whole second statement, and an interval-only rule would suppress that
statement's real `UPDATE -> bil_invoices` position and reach **PASS exit 0** — a new false
clean of exactly the R2-N01 class. Check 3 rejects that region because `bil_invoices`,
`mem_a`, `mem_b` and `x` are not privilege names.

**D6.8.3 — The suppression predicate, exactly.** A signal match `kw` yielded by any
`_TABLE_POSITION_SIGNAL_SOURCES` entry is suppressed **if and only if all four** hold:

1. `kw.group().upper()` is in D6.8.1's derived suppressible set; **and**
2. there exists a positively-computed region `R = [a, b)` per D6.8.2 with
   **`a <= kw.start()`** and **`kw.end() <= b`** (the match lies wholly within `R`; the
   upper comparison uses `kw.end()`, not `kw.start()`); **and**
3. `kw.start()` sits at **parenthesis depth 0** relative to `a`; **and**
4. nothing else. There is no token-content check on what follows `kw`, no spelling test
   against `ON`/`STDIN`/role names, and no fallback.

Condition 3 is normative and independently load-bearing. Measured: in
`GRANT SELECT (UPDATE bil_invoices) ON mem_t TO r` the `UPDATE` sits at depth 1 and resolves
to the real cross-domain `bil_invoices`; removing the depth-0 restriction suppresses it and
loses that reference.

**D6.8.4 — Uncertainty fails closed, in D6.7.2's own form.** Where the privilege-list region
cannot be positively computed — a dangling verb, a missing object `ON`, an unparseable
modifier, an unbalanced or ambiguous parenthesis depth, a quoted token at depth 0, a decode
failure, or **any other uncertainty whatsoever** — the signal is **RETAINED**, and the
D6.7.2 accounting sees the retention exactly as it sees any other recognised position. The
invariant, in the same form D6.7.2 uses:

> For any statement text T, the gate's outcome under D6.8 must be **no weaker** — on the
> ordering `clean < FAIL/ERROR` — than its outcome under the pre-D6.8 extractor, **except**
> in the one bounded class D6.8.5 licenses. **Absence of a positively-computed bound never
> implies suppression.** Suppression is permitted only *on* a bound, never *for want of*
> one.

Two further consequences bind the implementer. First, where suppression empties a statement's
position stream, the **D6.3 I-1 backstop still governs** and the statement remains ERROR:
`_implies_table_position` is `True` for every `GRANT`/`REVOKE` carrying an `ON` (verified
directly this session, via `_has_bare_table_verb_form`), so D6.8 can never convert a refusal
into a clean pass by emptying the stream. Second, D6.8 **adds no code path that can produce
a clean outcome that the pre-D6.8 extractor did not already compute from a real position** —
it only removes positions, and only the ones D6.8.5 proves carry nothing real.

**D6.8.5 — The losslessness rule, and the one bounded outcome change D6.8 licenses.** This
addendum is the only place in ADR-011 where a clause *removes* refusal surface, so the
"impossible to weaken the gate" monotonicity argument available to D6.1 and D6.7 is **not
available here** and is not claimed. The safety argument is instead the conjunction of
bounded losslessness, retention on uncertainty (D6.8.4), the ordering constraint (D6.8.6),
and the control corpus (D6.8.7). Losslessness is **constructive**, not merely empirical:

> Inside a positively-computed region at depth 0, every identifier-shaped token is a
> privilege name (D6.8.2 check 3). Therefore the element offset immediately following a
> suppressed signal can hold only another privilege word, a `,`, a `(`, or the region's
> terminating object `ON` — **never a table name**, because a table name at depth 0 would
> have rejected the region. A table-shaped name can appear only at depth ≥ 1, where
> suppression is forbidden (D6.8.3 condition 3), or outside the region, where no suppression
> applies.

Three corollaries, each measured:

- **`GRANT UPDATE ON x` still yields the real `ON -> x` position.** The suppressed signal's
  own identifier was the reserved word `ON`, which PostgreSQL forbids as an unquoted table
  name; a table genuinely named `"ON"` is quoted, is reached by the object-`ON` signal, and
  still yields (measured: `GRANT UPDATE ON "ON" TO r` retains `ON -> "ON"`).
- **Ordinary `UPDATE <table> SET …` and `… REFERENCES <table>` positions lie outside every
  region by construction**, since `<table>` at depth 0 rejects the region.
- **A parenthesised column list was never a position.** The lexer does not read into `(`, so
  `GRANT UPDATE (c1, c2) ON t` already carried an *unresolved* `UPDATE` position; suppressing
  it removes a refusal whose entire basis was the absence of an identifier.

**The exact, and only, outcome change D6.8 authorizes.** Let `O(T)` be the gate's outcome
for statement text `T` under the pre-D6.8 extractor and `O'(T)` under D6.8. Then
`O'(T) < O(T)` on the ordering `clean < FAIL/ERROR` is permitted **if and only if** every
position present in `O(T)` and absent from `O'(T)` was contributed by a signal suppressed
under D6.8.3, **and** each such signal's own position was either unresolved or resolved to
the unquoted reserved word `ON` (case-insensitively). In every other case
**`O'(T) = O(T)`**. In no case may `O'(T)` be clean where `O(T)` named a cross-domain or
unattributed **table**. Where no region is positively computed, `O'(T) = O(T)` identically
and D6.8 contributes nothing. This conditional is the testable statement of D6.8's safety and
must be pinned as a named invariant test, not merely documented.

**Exit-code movement that is not a weakening, disclosed so it is never misread.** Row 2C
`GRANT UPDATE ON bil_invoices TO r` moves from **ERROR exit 2** (status dominated by a
state-6 ERROR on the fake table `ON`) to **FAIL exit 1 `CROSS_DOMAIN_SQL_IMPORT` naming
`bil_invoices`**. `FAIL` and `ERROR` sit at the **same** level of the `clean < FAIL/ERROR`
ordering — both fail CI, which is what §24.1 requires — and the FAIL is strictly more
precise. Row `GRANT UPDATE ON ALL TABLES IN SCHEMA s TO r` keeps **ERROR exit 2** but changes
*reason*, from state 6 on `ON` to the D6.3 I-1 backstop. Both must be asserted by the
implementer, not discovered.

**D6.8.6 — The single suppression site, and why it is the merge point (normative).** The
predicate is implemented as **one** pure function and consulted at **exactly one** call
site: inside `_table_position_results`' `for source in _TABLE_POSITION_SIGNAL_SOURCES` /
`for kw in source(text)` loop, between obtaining `kw` and calling
`_positions_for_signal(text, kw)`. It may **not** be implemented inside an individual signal
source, and may not be duplicated.

Three reasons, all normative:

1. The two measured colliding tokens arrive from **different sources** — `UPDATE` from
   `_table_keyword_position_matches` (index 0) and `REFERENCES` from a bare
   `_REFERENCES_KEYWORD_RE.finditer` (index 1). A per-source filter would be written twice
   and could drift onto two answers for one text.
2. Index 1 is a bare regex method, so making it context-sensitive would require authoring a
   **new wrapper** — a further pre-accounting filter in precisely the blind spot the
   root-cause record §3.5 identifies as the structural cause of this whole lineage
   ("signal production and signal suppression both happen upstream of that accounting
   seam").
3. At the merge point the suppression is a **single accounting-visible decision** over the
   union of all sources, present and future: a source family added later inherits the
   predicate automatically and cannot escape it, and one mutation control covers the whole
   class.

**Accounting visibility is not optional.** Because D6.8 removes positions, the suppression
must itself be countable at that site and **disclosed under D8 on every run including PASS**:
the number of privilege-list signals suppressed under D6.8. A narrowing that leaves no trace
in the report is indistinguishable, to a reader, from the silent under-extraction D6.7 exists
to forbid.

**D6.8.7 — Ordering is a binding constraint, mechanically checked before D6.8 is applied.**
Half (1) — the anchored, positively-computed `_revoke_grantee_exclusion_offset` bound — must
land **first or alone**. D6.8's narrowing must **never** land before it, because root-cause
record §5 **measured** that doing so widens the demonstrated false-PASS surface from
`REVOKE SELECT …` to the `REVOKE UPDATE/REFERENCES …` spellings while every test stays
green. This is a normative clause, not advice.

The implementer must **re-verify** the precondition rather than assume it, by both of these
observations, before applying any part of D6.8:

- `_revoke_grantee_exclusion_offset("REVOKE SELECT ON mem_roster\nSELECT a FROM bil_invoices", <the REVOKE match>)`
  returns **`None`**; and
- gate row **1A** (that same text, on both the `.py` and `.sql` surfaces) exits **non-zero**.

If either observation fails, **D6.8 must not be applied**, and the dispatch stops and reports
the failed precondition. Both were satisfied in source `8cb5790a…` when this addendum was
decided.

**D6.8.8 — D8 truthfulness (tying back to D6.7.5).** What D6.8 **permits** the report to
say: that the privilege-word inflation and duplication of row 2D are resolved — the measured
figure moves from 4 reported references to the 2 that exist, and the duplicated
`CROSS_DOMAIN_SQL_IMPORT` line collapses to one — because the duplicate's specific cause was
`_LIST_POSITION_SIGNALS` membership of the privilege word, and D6.8 removes that signal
rather than de-duplicating after the fact. What D6.8 **still may not** say: that the
table-reference figure is **complete**. **D6.7.5 is unchanged and unweakened.** The figure
remains a disclosed **lower bound** until a run has established that D6.7.2's accounting
held for **every** subject, which D6.8 does not establish and does not claim. In addition,
the report must disclose the D6.8 suppression count per D6.8.6. **No clause of this addendum
authorizes asserting completeness that was not established, and no reduction in the reported
figure may be presented as evidence of completeness** — a smaller figure that is nearer the
truth is still a lower bound.

## Alternatives rejected for this addendum

| Alternative | Consequence | Verdict |
|---|---|---|
| Do nothing — leave the over-extraction as a deliberate backstop | It is an *accidental* backstop over a subset of one surface (root-cause §5) and, now that half (1) has landed, it backstops nothing: rows 1A and 3A both reach FAIL exit 1 naming `bil_invoices` without it (measured). Keeping it means a legitimate own-domain grant (2A/2B) is permanently refused naming a table nobody wrote, 2C's denial is mislabelled at status level against SCN-MOD001-007, and D8's figure stays inflated and duplicated against D6.7.5 — paying a real precision and truthfulness cost for no retained safety | **Rejected** |
| Make the individual signal sources privilege-context-sensitive instead of suppressing at the merge point | Writes the same predicate twice (index 0 and a new index-1 wrapper), adds a further pre-accounting filter in the exact blind spot root-cause §3.5 names as this lineage's structural cause, and leaves every future signal family to re-derive it. The TRUNCATE source's own privilege exclusion is the precedent *and* the warning: it reaches `GRANT TRUNCATE ON t` but not `GRANT TRUNCATE, SELECT ON t`, which this session measured as still spurious | **Rejected** — D6.8.6 fixes the one site |
| Remove `UPDATE`/`REFERENCES` from `_TABLE_KEYWORD_RE` / `_LIST_POSITION_SIGNALS` wholesale | Measured unsound, not merely inelegant: rows 2F `UPDATE bil_invoices SET x = 1` and 2G `CREATE TABLE mem_t (c int REFERENCES bil_invoices)` are at exit 1 **because** those keywords are in the vocabulary. Removing either converts a measured FAIL into a false clean — strictly worse than the ERROR noise removed, and exactly what D6.7.4 means by "vocabulary is a floor, not the mechanism" | **Rejected** |
| Special-case the literal `ON` identifier at attribution time (treat a position resolving to `on` as clean, or as no position) | Content-based, not positional, so it cannot distinguish the spurious `UPDATE -> ON` from a real table quoted `"ON"`, and it silently blesses *any* future signal that happens to resolve to `ON`. It also installs a token-name allowlist at the attribution layer — a D9-prohibited shape wearing a lexer's clothing, and the same anti-pattern the COPY decision already forbade for `STDIN`/`STDOUT`/path spellings | **Rejected** |
| Defer to the D9 third-party SQL parser | D9's deferral stands; a parser is a `CAPABILITY_POLICY.md` capability with a registry row. D6.8 is stdlib-only lexical work — a closed-vocabulary scan, parenthesis-depth tracking and interval membership — measured feasible without one | **Rejected**; D9 unchanged |
| Narrow D6.1's trigger to reduce the ERROR rate instead | Trades a loud refusal for a silent skip — the exchange D6.1 was written to forbid and the D6.7 addendum already rejected and **forbade to the implementer**. It remains forbidden | **Rejected, and forbidden** |
| Interval-only region bound, without D6.8.2's closed-vocabulary check | Measured to produce a **new false clean**: `GRANT SELECT`⏎`UPDATE bil_invoices SET x FROM mem_a JOIN mem_b ON mem_q` reaches PASS exit 0, since `_grant_revoke_object_on_match` spans the whole unrelated statement in an unsplit subject. The interval alone is not a bound | **Rejected** — the vocabulary check is load-bearing |
| Hand-list the suppressible tokens as `{UPDATE, REFERENCES}` | Omits the measured `GRANT TRUNCATE, SELECT ON t` residual and, worse, cannot notice a future signal keyword that is also a privilege name. D6.8.1's derived-set-plus-identity-assertion catches that by a failing test | **Rejected** — derive the set |

## Addendum conformance determination

Conforms to **Blueprint > TSD v1.4.1 > design bundle > EIP v1.4.1**. The two governing
passages were re-read first-hand this session from `knowledge/00-System/TSD_MIRROR.md`
(§24.1's gate-2 paragraph and §6.3's "rejects reverse synchronous imports **or direct
repository/table coupling**"), and `verify_baselines.py` returned **PASS 4/4** against
`PROJECT_INDEX.md`. D6.8 changes:

- **no TSD scope.** §24.1's allow-list is about what a module *may reference*. D6.8 removes
  from the stream a token that references nothing — a privilege name — while leaving every
  real table position, including the `GRANT`/`REVOKE` object target itself, in place. It
  moves the implementation *toward* §24.1 by letting the gate name the right subject (2C/2D),
  and away from nothing.
- **no domain model.** No directory is bound to any domain code, prefix, or schema; no
  `contracts/modules/ownership.json` is authored or made authorable. This ADR's scope limit
  and its **"fixture-scoped; real-tree domain ownership DEFERRED"** obligation are inherited
  verbatim.
- **no product, pricing, or business decision.** A CI lint's lexical extraction rule is none
  of these.
- **no module scope.** GOV-01-R04 already requires gate 2 with a deliberate-violation
  fail-closed proof; D6.8 makes that proof *name the right thing* rather than extending it.
- **no routing change.** ADR-005 is unchanged. Implementation remains `veyro-implementer`
  (Sonnet): every obligation above is a concrete bounded rule with a stated expected outcome
  and a closed corpus, and ADR-005 Decision 1's Opus-critical MOD-001 slices do not include
  gate 2's SQL extractor. **DC-17's routing-change sub-clause is therefore not triggered.**
  Judged, not assumed.
- **no capability.** Stdlib-only: a closed-vocabulary token scan, parenthesis-depth tracking
  and interval membership, all lexically decidable with functions already present. **D9's
  third-party-parser deferral stands**, so no `CAPABILITY_POLICY.md` lifecycle is opened and
  no registry row is needed.

**The one argument not available here, stated plainly.** Unlike D6.1 and D6.7, D6.8
**removes** ERROR surface. The claim "it is impossible for this clause to weaken the gate" is
therefore **not available and is not made**. The actual safety argument is the conjunction of
four independently testable parts: (i) **bounded losslessness** (D6.8.5), argued
constructively from the closed vocabulary and verified over 425 SQL-shaped literals drawn
from the live source and test files — exactly 4 deltas, every one an intended removal of a
spurious privilege-word signal, zero real identifiers lost — and over 3,456 generated
GRANT/REVOKE × statement × suffix × joiner combinations with **zero** losslessness violations
and **zero** fail-open violations; (ii) **retention on uncertainty** (D6.8.4), with the D6.3
I-1 backstop verified to still govern the emptied-stream case; (iii) the **ordering
constraint** (D6.8.7), mechanically checked before application; and (iv) the **finite
two-surface control corpus and the six verified-killable mutants** (D6.8.9 below). Remove any
one and the clause is not safe. All four are obligations on the dispatch, not observations.

D6.8 incurs **no spend**, uses **no real member data** (synthetic fixtures only; every probe
behind this decision ran from throwaway files under `/tmp/veyro-d68-probe/`), touches **no
production**, and asserts **no material product, pricing, business, architecture, or scope
change**. **No owner approval is required** — reasoned, not asserted: the amending authority
is this ADR's own Follow-up delegation plus D6.7.1's explicit "requires its own recorded
decision"; the subject matter is the gate-2 input contract's extraction semantics, which
Verdict B's split already placed with `veyro-lead` ("schema and semantics only, binding no
real domain"); and D6.8 is strictly narrower than both ADR-011 and the D6.7 addendum, neither
of which required owner approval.

The one owner-reserved item on this surface — binding the six `backend/app/modules/`
scaffolds to domain codes and owned table prefixes — remains **`BLOCKED:
OWNER_APPROVAL_REQUIRED`**, is untouched, and is **not** a dependency of this addendum.

## D6.8.9 — Acceptance corpus and mutation controls

Fixture convention, unchanged from this ADR's existing corpora: two modules,
`membership`/COM-01/`mem_` and `billing`/COM-03/`bil_`, `default_schema: "public"`, **no**
cross-module Python import anywhere, so the table identifier is the sole cross-module signal.
**Every row must be asserted both as a `.py` string literal and as a `.sql` file** — this
project's standing dual-surface convention.

**Expected outcomes below are derived from the position streams this session measured
directly, composed with ADR-011 D3.2/D6.3/D7's mapping — they are NOT gate-level
measurements.** The implementer must measure each one. **A row whose measured outcome differs
from this table is a stop-and-report, never a table edit.**

### Positive controls — must be clean, exit 0, so the narrowing is not vacuous over-ERRORing

| # | SQL | Required outcome |
|---|---|---|
| D68-P1 | `GRANT UPDATE ON mem_roster TO r` | **PASS exit 0** — row 2A inverted; was ERROR 2 on the fake table `ON` |
| D68-P2 | `GRANT REFERENCES ON mem_roster TO r` | **PASS exit 0** — row 2B inverted |
| D68-P3 | `GRANT SELECT ON mem_roster TO r` | **PASS exit 0** — row 2E, unchanged; isolates the privilege word as sole cause |
| D68-P4 | `GRANT UPDATE (c1, c2) ON mem_roster TO r` | **PASS exit 0** — column-level grant; the suppressed `UPDATE` position was unresolved |
| D68-P5 | `GRANT TRUNCATE, SELECT ON mem_roster TO r` | **PASS exit 0** — the shape the TRUNCATE source's own exclusion does not reach |
| D68-P6 | `REVOKE GRANT OPTION FOR UPDATE ON mem_roster FROM r` | **PASS exit 0** — two verbs, one shared object `ON`, overlapping regions |
| D68-P7 | `SELECT a FROM mem_roster, mem_events` | **PASS exit 0** — this ADR's named standing control; must stay PASS |
| D68-P8 | `SELECT a FROM mem_x JOIN mem_y USING (id)` | **PASS exit 0** — this ADR's named standing control; `USING (col)` is a column list; must stay PASS |
| D68-P9 | `GRANT ALL PRIVILEGES ON mem_roster TO r` | **PASS exit 0** — vocabulary modifier words accepted |

### Negative controls — must fail closed, with the exact code asserted

| # | SQL | Required outcome |
|---|---|---|
| D68-N1 | `UPDATE bil_invoices SET x = 1` | **FAIL exit 1 `CROSS_DOMAIN_SQL_IMPORT`** — row 2F, the ordinary `UPDATE` table position; unchanged |
| D68-N2 | `CREATE TABLE mem_t (c int REFERENCES bil_invoices)` | **FAIL exit 1 `CROSS_DOMAIN_SQL_IMPORT`** — row 2G, §6.3's textbook foreign key; unchanged |
| D68-N3 | `GRANT UPDATE ON bil_invoices TO r` | **FAIL exit 1 `CROSS_DOMAIN_SQL_IMPORT` naming `bil_invoices`** — row 2C; the disclosed ERROR 2 → FAIL 1 movement of D6.8.5. The cross-domain grant object must still be named correctly |
| D68-N4 | `GRANT SELECT, INSERT, UPDATE ON mem_a, bil_invoices TO r` | **FAIL exit 1 `CROSS_DOMAIN_SQL_IMPORT` emitted ONCE**, and D8 reporting **2** table references, not 4 — row 2D's inflation and duplication resolved |
| D68-N5 | `GRANT SELECT`⏎`UPDATE bil_invoices SET x FROM mem_a JOIN mem_b ON mem_q` | **FAIL exit 1 `CROSS_DOMAIN_SQL_IMPORT` naming `bil_invoices`** — the region-rejection row. **This is the row that proves D6.8 cannot be used to launder a real cross-domain reference by over-spanning a region**, and the row an interval-only rule turns into PASS exit 0 |
| D68-N6 | `GRANT SELECT`⏎`CREATE TABLE mem_t (c int REFERENCES bil_invoices) ON mem_q` | **FAIL exit 1 `CROSS_DOMAIN_SQL_IMPORT`** — the same hazard with `REFERENCES` at depth 1 |
| D68-N7 | `GRANT SELECT, UPDATE ON bil_invoices TO r` | **FAIL exit 1 `CROSS_DOMAIN_SQL_IMPORT`** — a suppressed privilege word beside a cross-domain object; the object is still named |
| D68-N8 | `GRANT SELECT (UPDATE bil_invoices) ON mem_t TO r` | **FAIL exit 1 `CROSS_DOMAIN_SQL_IMPORT` naming `bil_invoices`** — the depth-1 row pinning D6.8.3 condition 3 |
| D68-N9 | `GRANT UPDATE ON` | **ERROR exit 2 `MODULE_DEPS_SOURCE_UNINSPECTABLE`** naming the dangling object-`ON` signal — the dangling refusal survives suppression |
| D68-N10 | `GRANT UPDATE ON ALL TABLES IN SCHEMA mem_private TO r` | **ERROR exit 2 `MODULE_DEPS_SOURCE_UNINSPECTABLE`** via the **D6.3 I-1 backstop** — the disclosed reason-change row: zero positions after suppression, still refused |
| D68-N11 | `REVOKE admin FROM r` | **ERROR exit 2 `MODULE_DEPS_TABLE_UNATTRIBUTED`** — the half-(1) grantee-exclusion non-vacuity control; unchanged |
| D68-N12 | `INSERT INTO mem_t SELECT x FROM mem_a, bil_invoices` | **FAIL exit 1** — unchanged; no region exists |
| D68-N13 | `DELETE FROM mem_roster USING bil_invoices` | **FAIL exit 1** — unchanged; no region exists |
| D68-N14 | `GRANT UPDATE ON "ON" TO r` | **non-zero, exact code asserted** — a table quoted `"ON"` is a *different* table under D3.1 and is still reached by the object-`ON` signal; losslessness in the adversarial case |

### The §5 interaction rows — what each must be now that half (1) has landed

| # | SQL | Required outcome |
|---|---|---|
| 1A | `REVOKE SELECT ON mem_roster`⏎`SELECT a FROM bil_invoices` | **FAIL exit 1 `CROSS_DOMAIN_SQL_IMPORT` naming `bil_invoices`**. It was PASS exit 0 before half (1) and must stay non-zero; D6.8 must not touch it (no suppressible token present) |
| 3A | `REVOKE UPDATE ON mem_roster`⏎`SELECT a FROM bil_invoices` | **FAIL exit 1 `CROSS_DOMAIN_SQL_IMPORT` naming `bil_invoices`** — was ERROR exit 2 naming the fake table `ON`. **This row is the measured answer to §5's masking question:** because half (1) landed first, removing the accidental backstop moves 3A from *refused for the wrong reason* to *refused for the right reason*, and widens nothing. If 3A is observed at exit 0, D6.8 is wrong and must be reverted, not adjusted |

### Mutation controls — a surviving mutant is a **blocker for the dispatch**, not a note

These continue §5.3's **M-E** series and subsume the root-cause record §7(c) mutant M-B3.
**Each was verified killable by this decision session against the named row**, so none is an
impossible obligation.

- **M-E8** — suppression predicate hardcoded true (every suppressible token suppressed
  everywhere, no region required) → must be killed by **D68-N1, D68-N2, D68-N5, D68-N6,
  D68-N8**.
- **M-E9** — D6.8.2's region-validity scan removed; the region accepted whenever an object
  `ON` is found → must be killed by **D68-N5**. *This is the single most important mutant:
  it is the one that reintroduces a false clean.*
- **M-E10** — D6.8.3 condition 3 removed; suppression permitted at any parenthesis depth
  inside the region → must be killed by **D68-N8**.
- **M-E11** — the uncertainty branch flipped: suppress when no region is positively computed
  → must be killed by **D68-N5**.
- **M-E12** — suppression moved out of the merge point into an individual signal source
  (index 0's wrapper only), so `REFERENCES` and `TRUNCATE` escape → must be killed by
  **D68-P2** and **D68-P5**.
- **M-E13** — the region's upper end narrowed to `verb.end()` (an empty region), making D6.8
  a silent no-op → must be killed by **D68-P1, D68-P2, D68-P4, D68-P5** and by **D68-N4**'s
  reference count.
- **M-E14** — the D8 suppression counter required by D6.8.6 hardcoded to zero, or the
  report's lower-bound wording for the table-reference figure replaced by an unconditional
  completeness claim → must be killed by a **report-text** assertion, in the same way
  **M-E6** already is; no behavioural test covers a note's wording.

**Two pinned-identity assertions, which are not mutants.** First, the suppressible set must
be asserted **equal** to D6.8.1's computed intersection. Second, the region's upper end must
be asserted **open** at `on.start()`, i.e. the object-`ON` match is asserted *not* a member
of any region. Stated separately because this session established that several plausible
interval mutations — widening the upper end to end-of-text, moving the lower end to 0, making
the upper comparison `kw.start() <= b`, or widening the suppressible set to all
`_LIST_POSITION_SIGNALS` — are **equivalent mutants** under the layered defences and cannot be
killed by any corpus row. **They must therefore be pinned by direct identity assertions
rather than demanded as mutation kills**, and the independent reviewer must not be told to
kill something unkillable. The honest consequence, recorded so it is not later mistaken for
redundancy: **D6.8.2's vocabulary check, not the interval arithmetic, is the load-bearing
defence.**

## D6.8.10 — Explicit non-expansion

D6.8 authorizes nothing beyond the above. It does **not** authorize:

- **Any third-party SQL parser.** **D9**'s deferral stands, unchanged and unreopened.
- **Any touch of D3.2 state 3, `cte_names`, the `cte_names` default, the live call site, or
  any resolution order.** The **U1/U2 B HOLD**
  (`evidence/implementation/GATE2-R1-D6-U1-U2-QUALIFIED-REDECISION-2026-10-05.md`) continues
  in force and governs that lane, **including its exhaustive §4 prohibition list and its
  non-negotiable four-item re-opening bar**. Live CTE state-3 wiring remains forbidden.
- **Any binding of a real directory to a domain code, table prefix, or schema**, and no
  authoring of `contracts/modules/ownership.json`. Owner-reserved, unchanged, not a
  dependency.
- **Any skip, exempt, allowlist, path-pattern, per-module, per-file or suppression path
  beyond the one bounded predicate of D6.8.1–D6.8.3.** The predicate is positional and
  derived from a closed vocabulary; it names no file, no module, no path and no table, and it
  cannot be configured, extended or disabled from outside the source. Nothing in D6.8 may be
  read as licensing a second suppression, and a request to widen it is a new decision, not an
  implementation detail.
- **Any narrowing of D6.1's trigger**, in any amount, for any reason.
- **Any weakening of D6.7.** D6.7.1–D6.7.7 stand in full. In particular **D6.7.5** is
  unchanged: the D8 table-reference figure remains a disclosed **lower bound**.
- **Any resolution of D3.3/D3.4's silence on state 3's position in the precedence order.**
  That question **remains logged, not decided**, exactly as D6.7.7 left it.

## Addendum follow-up

**For the gate-2 implementer (`veyro-implementer`, Sonnet):** implement D6.8.1–D6.8.6
literally, in one bounded increment, in this order.

1. **First**, re-verify D6.8.7's two ordering observations. If either fails, stop and report;
   do not apply D6.8.
2. Implement the predicate as one pure function, consulted at the one call site D6.8.6 names.
   Names are yours to choose per existing conventions; the call-site location, the derived
   set, the region definition and the four predicate conditions are **normative**.
3. Author the D6.8.9 corpus — positives, negatives and both §5 interaction rows — each on
   **both** surfaces, each asserting an **exact outcome code**, each reading its own fixture
   back to prove the intended construct is present.
4. Kill **M-E8…M-E14** and add the two pinned-identity assertions. A surviving mutant is a
   **blocker for the dispatch**, not a note. Demonstrate non-vacuity by reintroducing the
   pre-D6.8 shape in a throwaway full-structure copy **outside** the repository and
   confirming each negative row then fails with the expected signature.
5. Wire the D6.8.6 suppression counter into D8 and confirm the table-reference figure is
   still worded as a **lower bound**.
6. Record source and test SHA-256 before and after; carry **"fixture-scoped; real-tree domain
   ownership DEFERRED"** on the face of the record; report the full test count and
   `ruff`/`py_compile`/`mypy` status honestly, including any pre-existing unrelated failures
   rather than normalizing them away; and state both disclosed deltas (D68-N3's ERROR 2 → FAIL
   1, D68-N10's reason change) as assertions rather than discoveries.

**DC-12 documentation corrections, required before any remediation record may claim this work
finished.** Each must be verified against the live file, not taken from this list:

- **`tools/validate_architecture_gates.py:262-264`** — the module docstring still reads *"An
  identifier no module owns is not flagged — only counted and disclosed in a note, since
  flagging it would false-FAIL on CTEs, aliases and catalog tables."* That is the exact
  "unowned ⇒ benign note" terminal state **D9** forbids *"in any form"*, documented as
  current behaviour. This session confirmed it is **still present**. The D6.7 Addendum
  follow-up already made its correction a precondition; it is restated here because it is
  still open, and leaving it standing is what would let a future session "restore" the
  behaviour these decisions exist to forbid.
- The same module docstring's **SQL-check paragraph** (the `_table_position_results`
  description, in the same docstring block) must name the D6.8 suppression, so the only
  stated contract a reader has is not silent about a narrowing.
- **`_revoke_grantee_exclusion_offset`'s docstring** and the corresponding test comment: half
  (1) corrected the false "same shape as COPY's" claim, which this session verified. Confirm
  it directly rather than on this addendum's word, and extend it to state that the exclusion
  and the D6.8 suppression are **two different mechanisms at two different layers** — an
  offset-equality filter inside index 0's wrapper versus a region predicate at the merge
  point — so they are never conflated into one "filter" a future increment copies into the
  wrong layer.
- **`_truncate_table_position_matches`'s docstring**: its privilege-`ON` exclusion is now
  partially redundant with D6.8. State which shape each mechanism reaches
  (`GRANT TRUNCATE ON t` versus `GRANT TRUNCATE, SELECT ON t`) rather than leaving a reader
  to assume one supersedes the other. Do **not** remove the source-level exclusion: the two
  defences are deliberately layered.

**For the independent round-3 reviewer (`veyro-code-reviewer`, Opus, fresh context):**
re-execute the full D6.8.9 corpus and the eleven-row reproducer of
`GATE2-R2-N01-N02-QUALIFIED-ROOT-CAUSE-2026-10-06.md` §2, and specifically try to **break
D6.8.5's losslessness conditional**: find any statement text in which D6.8's suppression
removes a position whose identifier was a real table rather than the reserved word `ON` or an
unresolved element. Concretely, attempt to (a) construct a text whose privilege-list region
is accepted by D6.8.2 yet contains a real table-shaped identifier at depth 0; (b) reach a
clean outcome by causing a region to over-span an unrelated statement; (c) get a suppression
taken where no region was positively computed; (d) empty a statement's position stream by
suppression and escape the D6.3 I-1 backstop; (e) make the D8 report assert completeness, or
omit the D6.8 suppression count, after a run in which suppression occurred; and (f) find a
suppression site other than the one D6.8.6 permits. Treat **D6.8.2's vocabulary check as the
primary attack surface** — this decision records it, not the interval arithmetic, as the
load-bearing defence, and records that several interval mutations are equivalent mutants.

**This addendum is an INPUT to that review, never an approval of it (DC-14).** It is not a
code review, not a security review, not a scenario verdict, and not a module certification.

**No scenario is promoted by this addendum.** SCN-MOD001-006/-007/-095/-096 remain **NOT
EXECUTED** and unpromoted. The round-2 **BLOCKED** verdict (P0=1/P1=1/P2=2/P3=2) **stands**.
**R1-F01 is NOT closed** and its blocker list is **not** reduced by this addendum — only by
the implementation and the independent assurance that follow it, against the criteria in
`GATE2-R2-N01-D67-REMAINING-SIGNAL-ROOT-CAUSE-2026-10-06.md` §7. MOD-001 remains
**uncertified**, **WIP=1** holds, and **MOD-002 stays locked**.

---
doc: GATE2-R1-QUALIFIED-LEAD-DECISION
module: MOD-001
work_unit: GOV-01-R04 — TSD §24.1 gate 2 (module-dependency / cross-domain SQL lint)
scenarios_in_scope: SCN-MOD001-006, SCN-MOD001-007, SCN-MOD001-095, SCN-MOD001-096
adjudicating_role: veyro-lead (registered architecture / ADR-decision role)
adjudicating_model: claude-opus-5[1m] — Opus 5 (1M context), as reported by this environment
date: 2026-10-05
type: QUALIFIED LEAD DECISION / REGISTERED-ROLE ATTESTATION — not an implementation, not a review, not a scenario promotion
subject: GATE2-R1-ROOT-CAUSE-STRATEGY-2026-10-05.md (provisional, model-attested-only)
overall_verdict: ACCEPTED WITH MANDATORY CORRECTIONS
adr_authored: ADR-011 (knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md)
---

# Gate-2 round-1 strategy — qualified lead decision

## 0. Attestation status (stated plainly, because it is the point of this record)

`GATE2-R1-ROOT-CAUSE-STRATEGY-2026-10-05.md` was **model-attested only**:
its front matter declares `authoring_model: claude-opus-5[1m]` and
`authoring_role: veyro-lead`, but it carried **no registered-role
attestation**. A declared role string inside a document is not the same
thing as the role having been exercised under dispatch. That report
therefore carried **no presumption of correctness** into this
adjudication, and it was not treated as one.

**This record is the registered-role attestation.** It was produced by a
bounded `veyro-lead` dispatch whose transport session was explicitly
forbidden from making the architecture judgment itself. The judgment
below is mine.

What I did **not** do: no `mr_verify.py` run against my own transcript
(self-attestation of model identity is worth little, and the tool is
owned by the orchestrating session — the orchestrator should run it
against this dispatch's transcript if a model attestation is wanted for
the record). No code, test, CI, fixture, or contract file written or
edited. No edit to the strategy report or the round-1 review — both are
left intact as evidence. No scenario promoted. No review round dispatched
or claimed; `REVIEW_IN_FLIGHT.md` read `CLEAR` at session start and was
left untouched. No commit, stage, or push. No `ownership.json`. No paid
service, no real member data, no deploy.

## 1. Session governance (performed first)

| Check | Result |
|---|---|
| `backend/.venv/bin/python knowledge/00-System/verify_baselines.py` | **PASS — 4/4** baseline hashes match `PROJECT_INDEX.md` (Blueprint `80f4b381…`, TSD `0d41c8a1…`, EIP `e5b5ec3b…`, design bundle `c96f77ab…`) |
| `SESSION_BOOTSTRAP.md` | read |
| `PROJECT_INDEX.md` precedence | read — Blueprint > TSD v1.4.1 > design bundle > EIP v1.4.1; MOD-001 is the active WIP=1 module |
| `CURRENT_STATE.md` / `CURRENT_HANDOFF.md` | read (live `current_as_of` heads; both exceed a full-read budget, as prior sessions also recorded) |
| WIP=1 | honored — MOD-001 only; MOD-002 untouched |
| Owner-reserved restrictions | honored; nothing in this adjudication requires any of the four. The real-tree ownership item stays `BLOCKED: OWNER_APPROVAL_REQUIRED` exactly as Verdict A left it |
| `REVIEW_IN_FLIGHT.md` | `current_claim: CLEAR`; no claim written (no review dispatched) |

No `BLOCKED` condition arises from this adjudication. The ADR it authorises
is schema-and-semantics only and binds no real directory to any domain.

## 2. Inputs actually read (dated)

**Adjudicated:**
- `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-ROOT-CAUSE-STRATEGY-2026-10-05.md` — in full
- `knowledge/03-Modules/MOD-001/evidence/code-review/GATE2-MODULE-DEPS-CODE-REVIEW-ROUND1-2026-10-05.md` — in full (verdict BLOCKED, P0=1/P1=7/P2=6/P3=7, reviewer `a4e01615878caa08c`, `claude-opus-5[1m]`)
- `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-ARCHITECTURE-DECISION-2026-10-05.md` — in full (the prior **binding** decision: Verdicts A/B/C/D)

**Governing text, read first-hand — not via secondhand citation:**
- **TSD §24.1 gate 2, extracted directly from the governing docx** `Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx` (`word/document.xml`), not only from `TSD_MIRROR.md`: *"Module dependency/SQL lint: application modules may reference only their owned table prefix/schema and approved read-model/application interfaces; cross-domain raw SQL/ORM imports fail CI. For the four intentional bidirectional pairs, §6.3 is the normative directed graph: only the listed synchronous edge may import/call the opposite application interface; the reverse edge must remain event-driven."*
- **TSD §6.3, extracted directly from the same docx**, four pairs (COM-01↔COM-03, DAT-01↔REL-01, GRO-01↔ENG-01, LIF-01↔GOV-04) and the normative rule: *"…only the synchronous direction listed above is allowed in the module import/application-call graph. The reverse edge is event-driven. CI dependency lint treats this table as the expected graph and rejects reverse synchronous imports **or direct repository/table coupling**."*
- **Mirror fidelity confirmed:** the docx text matches `TSD_MIRROR.md` §24.1 (≈11595-11625) and §6.3 (≈1515-1580) for both passages. The mirror is faithful on the gate-2 normative text; prior citations of it were accurate.
- `knowledge/03-Modules/MOD-001/REQUIREMENTS.md` 234-292 — `GOV-01-R04` scope/evidence/acceptance, including "no gate is bypassable at the **CI-workflow-configuration layer**"
- `knowledge/03-Modules/MOD-001/SCENARIOS.md` 405-412 (SCN-006/007) and 1894-1905 (SCN-095/096) — all four acceptance texts
- `knowledge/04-Decisions/ADR-009-permission-lint-input-contract.md` — in full, as the structural precedent for a gate input-contract ADR
- `knowledge/04-Decisions/` listing — next free ADR id verified as **011** by `ls` (ADR-001…ADR-010 present)

**Code facts I verified by direct read/execution rather than adopting from the review:**
- `tools/validate_architecture_gates.py:1594-1608` `_resolve_owner` — confirmed: a dotted identifier consults `owned_schemas` only and returns `None` without ever testing `owned_table_prefixes`; bare matching uses case-sensitive `startswith`. **R1-F01 is real.**
- `:1369-1371` `_TABLE_IDENT_RE` — confirmed `(?i)` with a two-segment ceiling, so uppercase identifiers are captured verbatim and 3-part names are mis-captured.
- `:1405-1412` manifest loop — confirmed the only key guard is `if name == SHARED_PACKAGE`. **R1-F08 is real**, and the reserved-name surface is narrower than the strategy assumes (see correction b5).
- `:1357,1362` — `SHARED_PACKAGE = "_shared"`; `_MODULE_NAME_IDENT_RE = ^[a-z_][a-z0-9_]*$`. **Executed:** `_root` fully matches this regex.
- `:805-808` and `:1265-1271` — confirmed both broad-funnel precedents the strategy cites exist, with the RLS one carrying the comment *"fail closed: any read failure is ERROR, never 'empty'"*. RC-3's framing is accurate.
- `:1770,1774` — confirmed both `read_text(encoding="utf-8")` sites sit outside any funnel. **R1-F07 is real.**
- **Executed regex check** of the strategy's own proposed prefix floor (§6 R1-F12): `^[a-z][a-z0-9_]*_$` **accepts `a_`**, and `pg_` also passes. Both are load-bearing against the strategy's stated intent — see corrections b3 and a2.

**Taken as given, not re-executed:** round 1's reproducer outputs, the 90/90 and 163/163 test counts, and the Ruff figures. Round 1 was independent, model-attested, and reported matching subject-file hashes before and after probing, so its observations are reliable inputs — but they remain its observations, not mine. **Not verified:** EIP §4.3/Appendix H, ADR-005/ADR-010 bodies, TSD Appendix I / DOM-001 (unverified in round 1 and still unverified here).

---

## 3. Per-invariant verdicts

### (a) SQL lexer scope — **ACCEPT WITH CORRECTIONS**

The boundary is correct and the "lexer, not parser, no new dependency"
decision is **upheld**. Three grounds survive scrutiny: the
`CAPABILITY_POLICY.md` cost is real and BUG-038 is the live precedent for
ignoring it; `tools/` genuinely has no dependency manifest, so adding one
is a structural decision and not a bug fix; and soundness comes from the
fail-closed caller, not from parser completeness. The
`_extract_table_refs(text) -> TableRefs | Uninspectable` seam with the
fail-closed contract held in the *caller* is the right design and makes
U-2 a one-function swap. The SQL-dialect limitation is disclosed on the
face of the report, which is the correct posture.

The scope is **sufficient** for the gate's totality claim and, with the
corrections below, **minimum necessary**. I-1 is the load-bearing idea and
it is correct: turning the verb set from a *detector allow-list* into a
*trigger over-approximation* is what ends the regex treadmill, because
widening it can then only ever produce more ERRORs.

**Corrections (binding):**

- **a1 — I-1's backstop is over-broad and must carve out the no-table
  statement class.** As written, "tripped the trigger but extracted zero
  table references ⇒ ERROR" makes `SELECT 1`, `SELECT now()`, `ANALYZE`
  and a bare `VACUUM` into ERRORs. Those are the most common operational
  SQL strings in existence (liveness probes above all), and a gate that
  ERRORs on `SELECT 1` generates exactly the pressure to weaken the gate
  that the strategy's own F10 disposition says this project's rules exist
  to resist. **Corrected rule:** ERROR if and only if the statement
  tripped the trigger **and** yields zero extracted table-position
  identifiers **and** contains at least one table-position keyword
  (`FROM JOIN INTO UPDATE TABLE ONLY REFERENCES`) or a bare-table verb
  form (`TRUNCATE`/`COPY`/`LOCK TABLE`/`DROP TABLE`/`ALTER TABLE`/`CREATE
  TABLE`/`GRANT … ON`). A triggered statement with no table position at
  all is clean, **counted, and disclosed** under its own report counter.
  This preserves the fail-closed property exactly — the dangling-keyword
  shape stays ERROR — while removing a guaranteed false-ERROR class.
- **a2 — I-2 state 4's "fixed closed set: `pg_*`" is self-contradictory
  and reachable.** A wildcard is not a closed set, and I verified by
  execution that `pg_` satisfies the strategy's own proposed prefix
  floor — so a module could declare `owned_table_prefixes: ["pg_"]` and
  make `pg_foo` ambiguous between state 1 (owned) and state 4 (system).
  **Corrected:** state 4 is specified as the exact schema names
  `pg_catalog`, `pg_temp`, `information_schema` plus PostgreSQL's own
  reserved `pg_` identifier prefix; the reserved check runs **before**
  ownership resolution; and `pg_`, `pg_catalog`, `pg_temp` and
  `information_schema` are rejected at manifest-parse time as
  `owned_table_prefixes`/`owned_schemas` values.
- **a3 — ACCEPT as stated:** ≥3-part identifiers ⇒ ERROR; unquoted ⇒
  casefold, quoted ⇒ preserve case (correct PostgreSQL semantics, and it
  makes quoted `"BIL_INVOICES"` correctly reach state 6); statement
  splitting on top-level `;`; dollar-quote, `E''`/`U&''`, and nested
  block-comment handling.

### (b) Manifest additions — **CORRECT** (two corrections are blocking)

The additions are the right *set* of fields, but as specified they are not
correct, not complete, and in one case they open a new hole in the gate's
headline invariant. This is the weakest of the five areas.

- **b1 — BLOCKING. `external_table_references` as specified is a
  manifest-layer allowlist over the gate's primary invariant.** Any
  module could declare another module's owned table as an "external
  reference" and take state 5's *clean* outcome. That contradicts three
  things at once: the tool's own input contract (*"Neither flag offers a
  skip, exempt, or allowlist path"*), `GOV-01-R04`'s "no gate bypassable
  at the CI-workflow-configuration layer" (this is a bypass one layer
  below it, which round 1 already identified as the live threat model for
  F04), and the governing §24.1 text *"may reference only their owned
  table prefix/schema and approved read-model/application interfaces"* —
  an arbitrary third table is not in that allow-list. ADR-009 D5 rejected
  precisely this shape for gate 4 and the same reasoning governs here.
  **Corrected:** an `external_table_references` entry that resolves to
  any module's `owned_table_prefixes` or `owned_schemas` is
  `MODULE_DEPS_GATE_INPUT_INVALID` at parse time; entries may only name
  identifiers no module owns; every declared entry is disclosed **by
  name** with a count in both text and `--json` on every run including
  PASS (ADR-009 D4.4's "visible inventory" pattern).
- **b2 — BLOCKING. `default_schema` plus `owned_schemas` creates a new
  fail-open, and the new ownership dimension has no ambiguity rule.** A
  module declaring `owned_schemas: ["public"]` would capture every
  `public.<anything>` as state 1 clean under the proposed
  "resolve `owned_schemas` first" ordering — swallowing exactly the
  cross-domain references R1-F01 is about. Separately, nothing adjudicates
  an identifier whose *schema* is owned by module A while its *prefix* is
  owned by module B. **Corrected:** (i) `owned_schemas` must be disjoint
  from the configured `default_schema`, enforced at parse time; (ii)
  resolution precedence is pinned — for a 2-part identifier whose schema
  equals `default_schema`, prefix resolution governs, otherwise schema
  ownership governs; (iii) a schema-owner/prefix-owner **conflict is
  ERROR**, never resolved by iteration order. See DRIFT-1 — (iii) is
  Verdict C's binding no-ambiguity rule carried into the widened
  ownership space.
- **b3 — The prefix specificity floor does not do what it says.**
  `^[a-z][a-z0-9_]*_$` is stated as "at least two characters before a
  mandatory trailing underscore" but **accepts `a_`** (verified by
  execution). **Corrected:** `^[a-z][a-z0-9_]+_$` (`+`, not `*`), which
  rejects `a_`/`a`/`ab` and accepts `ab_`/`mem_`/`bil_`. Two consequences
  the implementer must carry: C-5 gains an `["a_"]` reject row (its
  current `a`/`ab`/`ab_` triple cannot detect this), and any corpus row
  inherited from round 1's P0 reproducer — which used module `a` owning
  prefix `a_` — must be re-expressed with a conforming prefix, or it will
  assert `GATE_INPUT_INVALID` where it means to assert `FAIL`.
- **b4 — Drop the "reject any module name that is a string prefix of
  another" clause.** It is not minimum-necessary and it regresses a
  behavior round 1 verified as **correct**: its surface-1 table records
  "`pos` vs `pos_extra` both directions correctly attributed". Banning a
  legal, correctly-handled configuration is over-correction. Validating
  the manifest key with `_MODULE_NAME_IDENT_RE` **alone fully closes
  R1-F08**, because with dots excluded, `target = remainder.split(".",1)[0]`
  can only ever yield a declared top-level name. (The directory-side case
  is already fail-closed: a directory literally named `pos.v2` becomes a
  discovered module with no manifest entry ⇒ ERROR.)
- **b5 — `_root` must be reserved.** The strategy introduces a reserved
  `_root` importer but never reserves the name. I verified the current
  guard is only `if name == SHARED_PACKAGE`, and that `_root` fully
  matches `_MODULE_NAME_IDENT_RE` — so a manifest could declare a module
  named `_root` and capture modules-root files. **Corrected:** the guard
  becomes a reserved set `{_shared, _root}`.
- **b6 — Manifest versioning is unaddressed.** The validator rejects
  unknown keys, so a manifest carrying the new fields would have been
  refused by the prior validator. **Decided:** `version` stays **1**. No
  committed manifest exists anywhere in the repository (round 1
  independently confirmed no `contracts/modules/ownership.json`), so there
  is no consumer to migrate and a bump would imply a migration obligation
  that does not exist. Recorded rather than left silent.

Consistency with existing repo conventions is otherwise good: the new
fields follow `parse_module_manifest`'s established closed-key /
fullmatch / named-`GateInputError` idiom, and the disclosure requirements
mirror ADR-009 D4.4.

### (c) Root importer and discovery totality — **ACCEPT WITH CORRECTIONS**

I-3 is sound and it **does** achieve totality rather than merely appearing
to, for the dimension it claims. The decisive design property is that it
is a **reconciliation of two independent enumerations**, not a single
traversal: a discovery bug therefore surfaces as
`MODULE_DEPS_UNATTRIBUTED_SOURCE` instead of a silent omission, which is
precisely the "a PASS cannot be distinguished from 'not looked at'"
defect round 1 found in F03/F04/F12/F18. Requiring every path to land in
exactly one bucket and printing all bucket counts makes a PASS
self-evidencing. The SCN-070 cross-cutting prohibition (no
`exists()`/`is_dir()`/`is_file()` may gate *whether* a scan happens,
because they swallow `EACCES`) is correctly carried over and is the right
lesson from the live NON_CONVERGING item; keeping the existing
`is_symlink()` *refusal* checks while banning skip-decisions is the
correct distinction.

**Corrections (binding):**

- **c1 — The stated rationale for scanning modules-root files is wrong,
  though the decision is right.** The strategy argues ERROR is "for the
  uninspectable, not the inconvenient" and that refusing `conftest.py`
  "would create a permanent real-tree ERROR for a legitimate file". But
  under its own `_root` semantics — owns no prefixes, so every attributed
  table reference is cross-domain — the outcome is a permanent real-tree
  **FAIL** (exit 1, `CROSS_DOMAIN_SQL_IMPORT`) for that same legitimate
  file the moment it references any owned table. Trading a permanent
  ERROR for a permanent FAIL is not the improvement the rationale claims;
  a FAIL asserts "a violation was found" about a legitimate file.
  **Decision: keep scanning (the outcome is correct — under §24.1 a file
  that owns nothing may reference nothing), fix the rationale, and add
  this to the strategy's §10 disclosed real-tree consequences** alongside
  the new ERROR surfaces, so it is never misread as a regression.
- **c2 — The second enumeration must not follow symlinks.** The strategy
  does not say. If the reconciliation walk follows a symlinked directory
  while the per-module walk refuses it, the reconciliation either
  manufactures a spurious unattributed bucket or enumerates **outside the
  fixture root** — regressing round 1's surface-6 containment finding.
  **Corrected:** the reconciliation enumeration does not follow symlinks
  and buckets each as refused ⇒ ERROR, identically to the per-module walk.
- **c3 — Totality must be stated as relative.** I-3 proves every path
  **under the supplied `--modules-dir`** is bucketed. It proves nothing
  about a wrong root, and a manifest-declared-but-absent module remains
  "only a note" per the existing contract. Both belong in the §9 coverage
  note; neither is currently there.
- **c4 — `_root` reservation** — as b5.

### (d) Error taxonomy — **CORRECT**

Well-intentioned and nearly complete: every code names a subject and a
location, severity maps to a fixed exit code, and no code maps to exit 0.
Those I accept. It is not yet well-formed on disjointness.

- **d1 — BLOCKING for the corpus to be falsifiable at all. The taxonomy
  overlaps, and the strategy itself records the overlap without resolving
  it.** C-1 says unprovable rows "must assert `ERROR` with the specific
  code (`MODULE_DEPS_SOURCE_UNINSPECTABLE` **or**
  `MODULE_DEPS_TABLE_UNATTRIBUTED`)". A disjunction defeats C-1's own
  governing requirement — "each row asserts an exact outcome code, not
  merely non-zero" — for exactly the rows where precision matters most.
  **Corrected: a total, disjoint decision rule.**
  `MODULE_DEPS_SOURCE_UNINSPECTABLE` iff reduction to statements/tokens
  **failed or was impossible** (runtime assembly, dynamic construct,
  node-level decode failure, dangling keyword, unlexable text).
  `MODULE_DEPS_TABLE_UNATTRIBUTED` iff lexing **succeeded** and produced
  ≥1 table-position identifier resolving to none of states 1-5. The
  discriminator is whether an identifier was actually extracted. Where
  both fire in one file, report both, partitioned, never collapsed (which
  is also the F09 closure).
- **d2 — Two codes are near-homonyms for unrelated conditions.**
  `MODULE_DEPS_UNATTRIBUTED_SOURCE` (a *file path* not accounted for by
  coverage) and `MODULE_DEPS_TABLE_UNATTRIBUTED` (a *table identifier*
  with no owner) differ by word order. In a report, a test name, or a
  mutation table they will be misread, and a misread code is an
  unactionable code. **Corrected:** rename the coverage code to
  `MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH`; keep
  `MODULE_DEPS_TABLE_UNATTRIBUTED`.
- **d3 — I-4's outermost funnel is not yet closed by construction.**
  Mapping any unexpected exception to a `GateReport(... ERROR ...)` that
  is "still printed/serialised before exit 2" leaves the emission
  dependent on the gate's own report and serialisation machinery being
  healthy — so a throw inside report rendering reproduces R1-F07's
  "non-zero with no report" one layer up. **Corrected:** the funnel's
  emission is a minimal last-resort path (literal text line plus a
  hand-built minimal JSON object under `--json`) that does not call back
  into the report builder, and it must not catch `SystemExit` or
  `KeyboardInterrupt` and must never yield PASS.

### (e) Corpus acceptance — **CORRECT**

The corpora are genuinely **falsifiable** in shape, and this is the
strategy's strongest contribution after I-1. Four mechanisms carry that:
exact-outcome-code assertions rather than `exit != 0` (which specifically
prevents a normalisation regression from passing by landing in a
different ERROR); C-7's read-back anti-vacuity on the fixtures themselves
(the F12 lesson applied to the tests); C-6's **per-branch** mutation
reporting with a surviving mutant as a dispatch blocker rather than a
note; and C-5's re-assertion of the three Verdict C cases, which makes
non-regression of a binding decision a test rather than a promise. They
**do close** round 1's findings rather than restate them: each finding
maps to a row asserting a specific code.

The decisive gap is on the other side of the ledger.

- **e1 — The mutation set tests only that the OLD fail-opens are closed,
  never that the NEW clean states are tight.** All twelve C-6 mutants
  attack the hardening. Nothing attacks states 3/4/5, `_root`, or the new
  counters — which are the fail-open surfaces *this strategy itself
  introduces*. **Required additional mutants:** widen state 4's reserved
  check from the `pg_` prefix to any `pg`-initial identifier; make state
  5 accept an `external_table_references` entry naming another module's
  owned table (this is the b1 bypass, and it must die in a test); widen
  state 3's CTE collection to accept any bare identifier as locally
  bound; give `_root` ownership so modules-root violations read clean;
  and hardcode a report counter non-zero (without this, F12(ii)'s
  "evidence must assert non-zero counts" obligation is a prose promise,
  since the tool deliberately does not enforce it).
- **e2 — C-5 is missing five rows** that the corrections above make
  load-bearing: `owned_table_prefixes: ["a_"]` (reject); `owned_schemas:
  ["public"]` against `default_schema: "public"` (reject); a
  schema-owner/prefix-owner conflict (ERROR); an
  `external_table_references` entry naming another module's owned table
  (reject); a manifest declaring a module named `_root` (reject).
- **e3 — C-1 cannot be contract-shaped until d1 lands.** Resolve the
  taxonomy disjunction first, then every C-1 row has exactly one legal
  expected code.
- **e4 — C-1 rows inherited from round 1's `a_`-prefix fixture must be
  re-expressed** under the corrected floor (b3).
- **ACCEPT as stated:** C-2 (all dynamic-import idioms ⇒ ERROR exit 2,
  including the blanket `exec`/`eval`/`compile` rule), C-3, and C-4 — and
  C-4's mode-000-**directory** rows are the correct and specific SCN-070
  regression guard, since that is the exact shape `Path.is_dir()` and
  `exists()` swallow.

---

## 4. Reconciliation against the round-1 code review

**Resolved outright (subject to this record's corrections):** R1-F02,
R1-F04, R1-F05, R1-F06, R1-F07, R1-F09, R1-F11, R1-F13, R1-F15, R1-F16,
R1-F17, R1-F18, R1-F20, R1-F21. Each gets a mechanism, not a widened
list, and each gets a corpus row with an exact expected code. F14 is
resolved as a mandatory evidence obligation (SCN-007's raw-table half,
which is the correct disposition — it is the literal subject of the
scenario).

**Resolved only with a correction attached:**
- **R1-F01 (P0)** — the three-part answer (schema stripping, PostgreSQL
  case semantics, and *independently* `None` ⇒ ERROR) is correct and the
  defence-in-depth framing is right: a normalisation regression lands in
  state 6, not in PASS. But it is incomplete without **a2** (reserved
  `pg_` collision) and **b2** (a module claiming the default schema would
  re-open the same hole from the other direction).
- **R1-F03** — right outcome, wrong rationale; see **c1**.
- **R1-F08** — closed by key validation, but the added string-prefix ban
  over-reaches and regresses verified-correct behavior; see **b4**.
- **R1-F12** — the floor regex does not implement its stated intent
  (**b3**), and the counter obligation needs a mutant to be real (**e1**).

**Not fully resolved — accepted as a partial closure, and must be labeled
as one:** **R1-F12(i)**, subject-level anti-vacuity. The strategy
deliberately declines to promote zero-subject to INCONCLUSIVE in the tool
("that would invent a new failure mode for a real tree we have not
modelled") and moves the obligation to the evidence set. **I uphold that
scoping** — inventing a real-tree failure mode on an unmodelled tree is
the worse error, and the counters plus evidence-set assertions do address
round 1's actual *evidentiary* concern. But it closes F12(i) by
relocation, not by elimination, and every artifact must say so rather
than claiming F12 closed.

**Misread by the strategy (two, both minor but real):**
- **R1-F19** — the strategy's disposition repeats Verdict D's "the 12
  `E501`" as if that were the count. Round 1 specifically measured **299**
  `E501` at ruff's default 88-column width and its whole point was that
  the figure is **config-dependent and not reproducible without pinning
  both config and line-length**. The strategy's *method* is right (pin a
  root `ruff.toml`, re-run, record the pinned figure, do not mass-fix in
  the same diff) but it carries forward a number round 1 falsified as a
  standalone claim. The implementer must record the figure **measured
  under the pinned config**, and must not restate "12".
- **R1-F10** — the claim that the residual risk (SQL hidden in a
  docstring and executed dynamically) "is itself caught by F05(iii)" is
  an overclaim: `cursor.execute(SomeClass.__doc__)` reaches the database
  with no `exec`, `eval`, or `compile` anywhere. The docstring exclusion
  is still the right call (a false FAIL on English prose is worse), but
  the residual must be disclosed **as a residual** in the coverage note,
  not as covered.

**No finding is deferred, and I uphold that.** The strategy's governing
rule — no finding whose observable shape is a silent exit 0 may be
deferred — is the correct standard for this surface and it is applied
consistently across all thirteen P2/P3 items.

**Severity:** I did not re-grade any round-1 severity. The P0/P1 set is
adopted as given.

---

## 5. Drift from the prior binding GATE2 architecture decision

Drift from a binding decision is a finding, not a free choice. Two exist.

**DRIFT-1 — substantive, must be cured before implementation.** Verdict C
adjudicated the no-ambiguity invariant — *"unambiguous attribution of a
table to exactly one owner"* — over a **one-dimensional** ownership space
(prefix versus prefix), deciding: accept same-module nesting, reject
cross-module overlap with no exception path, reject exact duplicates. The
strategy **widens that space** — `owned_schemas` resolved first,
`default_schema` stripping, and `external_table_references` as a third
clean path — without carrying Verdict C's rule into the new dimensions.
That silently narrows a binding decision's reach: overlap is still
rejected between prefixes, but a schema/prefix conflict and an
external-reference/owned-table collision are both newly reachable and
both unadjudicated. **Cured by b1 (disjointness, enforced) and b2(iii)
(conflict ⇒ ERROR, never resolved by iteration order), which is simply
Verdict C's own rule extended to the space the strategy created.** Both
are bound in ADR-011.

**DRIFT-2 — procedural, ACCEPTED with this record.** Verdict D decided
"**one** bounded implementer dispatch, then a gate-2-scoped independent
code review, then scenario review." The strategy proposes **three**
implementation dispatches (D1a, D1b, D2). I accept this, for two reasons
that must be on the record rather than assumed: Verdict D's five named
items are complete and round-1-verified (its own assurance table confirms
items 1-3 and item 5), so the dispatch Verdict D authorised is *finished*
and this is a new tranche rather than an amendment of it; and Verdict D's
assurance table expressly contemplates this path — a reviewer finding "is
adjudicated by a fresh lead dispatch, not by the implementer," which is
this dispatch. The split is also the better engineering call (smaller
review surfaces against a unit whose prior guarded attempt timed out
mid-edit). **Recorded as a superseding sequencing decision under Verdict
D's own mechanism, not as a silent re-plan.**

**No drift found on:** Verdict A (real-tree ownership stays DEFERRED and
owner-blocked; the strategy's §10 OWNER row preserves it verbatim);
Verdict A's five-item fixture-scoped evidence set (extended, not
narrowed, and the "fixture-scoped; real-tree domain ownership DEFERRED"
labeling obligation is carried); Verdict A.4 (premise confirmed moot by
round 1 — no `.github/workflows/` exists; "inventing a skip/exempt path
remains forbidden" is restated); Verdict B (ADR is schema-and-semantics
only, no owner approval, routed to a separate lead dispatch — this one);
Verdict C's three cases (re-asserted unchanged as C-5 rows); Verdict D
items 1-3 including the explicit "do not mass-fix the 12 `E501` in the
same diff"; and Verdict D's assurance order (code review → scenario
review → no gatekeeper, since gate 2 is one of seven).

---

## 6. Overall verdict

**ACCEPTED WITH MANDATORY CORRECTIONS.**

The root-cause analysis is **correct and is the strategy's real
contribution**: the twenty-one findings are not twenty-one defects but
one error — *an unknown is treated as benign* — in four dimensions (input
syntax, extent, readability, identity). The remediation follows from that
correctly: a **polarity inversion** from "recognise-known-bad, else PASS"
to "prove-clean, else VIOLATION or ERROR", not a widening of regexes and
name lists. That is the right call, and it is the one call that matters,
because widening would have moved all twenty-one shapes without removing
any cause — the same failure mode the SCN-070 convergence assessment
already recorded on a different surface. The ERROR-on-unknown bias is
correctly justified by cost asymmetry (a false ERROR costs a
conversation; a false PASS puts a wrong claim into a module certificate),
and the §3 disclosure that **gate 2 is not a security boundary** is both
true and necessary.

It is **not** accepted as written. Three corrections are **blocking** and
must land in the input-contract ADR before any implementation dispatch:

1. **b1** — `external_table_references` is a manifest-layer bypass of the
   gate's headline invariant unless constrained to identifiers no module
   owns, with per-name disclosure.
2. **b2** — `default_schema`/`owned_schemas` lets one module capture the
   default schema and leaves schema-versus-prefix conflicts
   unadjudicated; this is also DRIFT-1's cure.
3. **d1** — the ERROR taxonomy overlaps, which defeats C-1's own
   exact-code requirement on precisely the rows that matter most.

Eleven further corrections (a1, a2, b3, b4, b5, b6, c1, c2, c3, d2, d3)
and four corpus corrections (e1-e4) are binding on the implementation.
Two round-1 misreads (F19's stale `E501` figure, F10's `__doc__` residual
overclaim) must be corrected in the implementation records rather than
carried forward. F12(i) must be labeled a relocation, not a closure.

**Scenario status unchanged.** SCN-MOD001-006/-007/-095/-096 remain **NOT
EXECUTED and unpromoted**. The round-1 **BLOCKED** verdict **stands**.
This record is an architecture decision and a registered-role
attestation — it is **not** code assurance, not a review, and not an
approval (DC-14). Nothing here promotes a scenario or accepts the gate.

**ADR authored:** `knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md`
(next free id verified by `ls`; ADR-001…ADR-010 present). It is **schema
and semantics only**, binds the gate-2 input contract **for fixtures**,
and binds **no real scaffold and no domain logic** — stated explicitly
inside the ADR.

## 7. Next legal action (single, crisp)

**Dispatch D1a — one bounded `veyro-implementer` (Sonnet) dispatch
implementing I-1 and I-2 plus the manifest additions, bound to ADR-011 as
its fixed input contract and to this record's corrections a1-a3, b1-b6,
d1-d2, e2-e4; corpora C-1 and C-5 with exact expected codes; no
`ownership.json`, no CI change, no scenario promotion, no commit.**

Then, in order, and not before: **D1b** (I-3 reconciliation, `_root`
importer, I-4 funnels including d3's last-resort emission, import binding
analysis, report counters and partitioned disclosure, the mechanical P3s;
corpora C-2/C-3/C-4) → **D2** (pinned root `ruff.toml` and a re-measured
figure per the F19 correction; regenerated fixture-scoped evidence set
including SCN-007's raw-table half; C-6 mutation controls reported
per branch, including e1's additional mutants, with any surviving mutant
a hard blocker) → **a fresh independent Opus `veyro-code-reviewer` round
2** over the combined diff, with an `IN_FLIGHT` claim written in
`REVIEW_IN_FLIGHT.md` **before** the dispatch call returns →
**`veyro-scenario-reviewer`** for the four scenarios. No gatekeeper
involvement (gate 2 is one of seven gates).

**Out of scope for every dispatch above, explicitly:**
`contracts/modules/ownership.json` and any domain binding (owner-reserved,
Verdict A, unchanged); any CI change; any scenario promotion; any SCN-070
or DOM-002 state, counter, or file.

**No `BLOCKED` condition applies to this adjudication.** The one
owner-reserved item on this surface — binding the six
`backend/app/modules/` scaffolds to domain codes and owned table prefixes
— remains `BLOCKED: OWNER_APPROVAL_REQUIRED` (material architecture
change) and is **not** on this path; nothing in `GOV-01-R04`'s acceptance
criteria depends on it being unblocked.

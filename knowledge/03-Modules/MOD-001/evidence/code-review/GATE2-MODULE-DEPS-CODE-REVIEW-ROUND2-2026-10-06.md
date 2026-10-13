---
doc: GATE2-MODULE-DEPS-CODE-REVIEW-ROUND2
module: MOD-001
work_unit: GOV-01-R04 — TSD §24.1 gate 2 (module-dependency / cross-domain SQL lint)
scenarios_in_scope: SCN-MOD001-006, SCN-MOD001-007, SCN-MOD001-095, SCN-MOD001-096
round: 2 (combined independent code review for this semantic unit; round 1 = GATE2-MODULE-DEPS-CODE-REVIEW-ROUND1-2026-10-05.md, BLOCKED)
date: 2026-10-06
reviewer_role: veyro-code-reviewer (fresh independent context, Opus tier)
reviewer_model: claude-opus-5[1m] — Opus 5 (1M context), as reported by this environment
verdict: BLOCKED
p0: 1
p1: 1
p2: 2
p3: 2
originals_closed: 13 of 14 tracked (R1-F01..F14); 1 closed-with-evidence-caveat
originals_still_open: R1-F16, R1-F17, R1-F19, R1-F20 (partial), R1-F21 (partial) — all P3, none in the live 14-finding projection
review_type: CODE ASSURANCE ONLY — no scenario PASS, no promotion, no module certification, no remediation
snapshot_source_sha256: b9e012a47a10935fc5dd390383b6907131c65be01372b5b02dc6d0b47e8e6484
snapshot_tests_sha256: 83779ff7c49626be57200374024f4b262879d86291b4d3b116581c4b38ac0288
---

# Gate-2 (module-deps) Combined Independent Code Review — Round 2

## 1. Verdict

**BLOCKED.**

| Severity | New this round | Count |
|---|---|---|
| P0 | R2-N01 | 1 |
| P1 | R2-N02 | 1 |
| P2 | R2-N03, R2-N04 | 2 |
| P3 | R2-N05, R2-N06 | 2 |

The round-1 remediation is substantial and, on the findings it set out to
close, genuinely effective: **13 of the 14 tracked original findings are
closed under independent execution**, and the fourteenth (R1-F14) is closed
at the code/test level with an evidence-currency caveat. Every one of
ADR-011's five directed round-2 attacks on the *manifest and output*
surfaces was repelled — I could not use `external_table_references`,
`default_schema`, `owned_schemas`, a reserved name, a dotted module name,
or a non-existent interface path as a bypass; I could not get a non-zero
exit with no report or invalid `--json`; and the D7.3 funnel, the D7.2
partition, and Verdict C's three cases all behave exactly as decided.

The block is a single defect, and it is the same invariant round 1 blocked
on, re-opened through a different layer. **ADR-011 D3.2 asserts that every
identifier in a table position resolves to exactly one of six states. It
does not.** The identifier *extractor* keys on a five-keyword set
(`FROM|JOIN|INTO|UPDATE|TABLE`) and takes one identifier per keyword match,
while the D6.3 I-1 backstop that is supposed to catch what the extractor
cannot reach fires only when **zero** identifiers were extracted. So as
soon as any one identifier in a statement extracts cleanly, every other
table position in that same statement becomes invisible. A cross-domain
raw-table reference in a comma-separated `FROM` list — ordinary ANSI SQL,
no exotic construct, no manifest cooperation — returns **PASS, exit 0**,
and the D8 report states its counts are "complete for this run."

That is the literal subject of SCN-MOD001-007, and it is the same
"silent exit-0 pass on the gate's headline invariant" standard round 1
applied to R1-F01. I would not defer it under any framing.

## 2. Snapshot verification

| | Start of review | After all probing | Match |
|---|---|---|---|
| `tools/validate_architecture_gates.py` | `b9e012a47a10935fc5dd390383b6907131c65be01372b5b02dc6d0b47e8e6484` | identical | yes |
| `tools/tests/test_validate_architecture_gates.py` | `83779ff7c49626be57200374024f4b262879d86291b4d3b116581c4b38ac0288` | identical | yes |

Both match the dispatch's pinned values and the snapshot named in
`GATE2-R1-F01-R2-READINESS-RECONCILIATION-2026-10-06.md`. Nothing drifted
mid-review. Both files remain untracked WIP, consistent with the decision
record and with round 1.

**Repository untouched.** `git status --porcelain` returned 425 entries;
the only entries referencing this review's subject are the two pre-existing
untracked targets. No probe artifact appears in the repository — every
fixture this review built lives under `/tmp/g2r2/`. No file was edited,
staged, committed or pushed. `REVIEW_IN_FLIGHT.md` was read and honored,
not written: its `current_claim` was pre-written for this dispatch
(operation `bcd46b31-b6a1-4fe5-8f26-3160e2ac45b5`), and clearing it remains
the orchestrator's action once this result is recorded.

## 3. Scope

**Reviewed:** the gate-2 manifest contract (`parse_module_manifest`,
`load_module_manifest`, `_manifest_path_kind`, `_resolve_interface_target`,
`_external_ref_conflict`); discovery and the three traversals
(`_modules_root_package`, `_discover_modules`, `_walk_module`,
`_root_level_files`, `_scan_namespace_subtree`,
`_enumerate_eligible_descendants`, `_reconcile_subtree_against_walk`,
`_reconcile_module_coverage`); the SQL trigger, lexer and attribution path
(`_is_sql_ish`, `_implies_table_position`, `_extract_table_identifiers`,
`_dangling_keywords`, `_split_identifier_segments`,
`_normalize_identifier_segment`, `_owner_by_prefix`, `_owner_by_schema`,
`attribute_table_identifier`, `_scan_sql_text`, `_scan_sql_statement`);
the uninspectable/dynamic-construct set; the D8 note builders; the
output/exit contract (`_finish`, `_emit_internal_error`, `main`); the
gate-2 tests; ADR-011 in full; the round-1 report; the U1/U2 qualified
redecision and the D8 coverage-gap disclosure; and the readiness,
soft-stop, round-counter and positive-evidence-set reconciliation records.

**Deliberately excluded (per dispatch bounds):** SCN-MOD001-070, DOM-002,
the RLS gate (`--gate rls`, ADR-010), the permission gate (ADR-009,
"permission A2"). Scenario-catalog design remains `veyro-scenario-reviewer`'s
role and is neither performed nor pre-empted here.

**The named U1/U2 B HOLD was treated as binding and is not re-litigated.**
I did not request, propose, design or implement live CTE state-3 wiring,
and I make no recommendation to reorder D3.2's precedence. I assessed only
the actual unwired state and its disclosure — see §6.

## 4. Disposition of every original round-1 finding

The live finding projection tracks **14** findings. The round-1 report
recorded **21** (P0=1, P1=7, P2=6, P3=7). The 14 tracked are R1-F01..F14;
the seven P3s (R1-F15..F21) sit outside the tracked set — itself a finding
(R2-N05). All 21 are reconciled below against executed evidence, not
against the implementer's claims.

### Tracked (R1-F01..F14)

| # | Sev | Disposition | Independent evidence |
|---|---|---|---|
| R1-F01 | P0 | **CLOSED** | `public.`-qualified → FAIL 1; `BIL_INVOICES` → FAIL 1; `Bil_Invoices` → FAIL 1; `"bil_invoices"` → FAIL 1; `"public".bil_invoices` → FAIL 1; `db.public.bil_invoices` → ERROR 2 (D3.3 rule 1). `"BIL_INVOICES"` → ERROR (correctly a *different* table under D3.1). Defence in depth confirmed: D3.1 normalisation **and** state-6 ERROR both present. **The finding as specified is closed; the invariant it protects is re-opened by R2-N01 at a different layer.** |
| R1-F02 | P1 | **CLOSED** | `ALTER/DROP/CREATE/LOCK TABLE` and `MERGE INTO` → FAIL 1 (attributed); bare `TRUNCATE`, `COPY`, `GRANT … ON` → ERROR 2 via the D6.3 backstop. 8/8 non-zero; none passes. The D6.1 trigger-verb over-approximation genuinely ends the regex treadmill for the *trigger*. |
| R1-F03 | P1 | **CLOSED** | Violation planted in `<modules-dir>/conftest.py` → `CROSS_DOMAIN_SQL_IMPORT: _root -> billing — conftest.py:1`, FAIL 1, `checked` rose 6→7. D4's `_root` importer scans root files rather than refusing them, and the permanent-FAIL consequence is disclosed on the report's face. |
| R1-F04 | P1 | **CLOSED** | `rogue/x.py` with no `__init__.py` → `MODULE_DEPS_COVERAGE_UNATTRIBUTED_PATH: rogue/x.py`, ERROR 2, citing PEP 420 by name. D5's two-direction reconciliation is real: it is a second independent `os.scandir` enumeration diffed both ways, not a re-read of discovery's own list. |
| R1-F05 | P1 | **CLOSED** | All 7 idioms ERROR 2: `importlib.import_module`, `from importlib import import_module`, aliased `im(...)`, `builtins.__import__`, `getattr(importlib, "import_module")`, `exec("from app.modules.billing.internals import s")`, bare `__import__`. The binding-resolution approach (per-file `_dynamic_import_bindings`/`_builtins_module_bindings`/`_importlib_module_bindings`/`_exec_bindings`) replaces name matching, so this is closed structurally, not by list extension. |
| R1-F06 | P1 | **CLOSED** | All 5 shapes ERROR 2: `" ".join([...])`, verb-interpolated f-string, `%`, `.format()`, `+` concat. The f-string message correctly names the runtime-assembly reason. |
| R1-F07 | P1 | **CLOSED** | Non-UTF-8 `.py` → `MODULE_DEPS_GATE_INPUT_INVALID` ERROR **2** naming `UnicodeDecodeError`, with a full report on both surfaces; `--json` parses and carries `status: ERROR`. Closed by construction via the single `_read_source_text`/`_read_gate_text` conversion plus D7.3's funnel, which I verified independently by forcing a synthetic `RuntimeError` inside the gate in-process: text and `--json` both → `MODULE_DEPS_GATE_INTERNAL_ERROR`, exit 2, valid JSON, never PASS. |
| R1-F08 | P1 | **CLOSED** | `pos.v2` → ERROR, "module name is not a valid identifier"; `_root` and `_shared` → ERROR, "reserved". D2's identifier validation closes the misattribution at source, exactly as ADR-011 reasoned, and the rejected prefix-ban alternative was correctly not adopted. |
| R1-F09 | P2 | **CLOSED** | Real `CROSS_DOMAIN_SQL_IMPORT` + one f-string in the same run → ERROR 2 with **both** lists present and a D7.2 partition note stating that the FAIL partition is a lower bound and that exit 2 does not imply zero FAIL-class violations. The lever to hide violations behind one f-string is gone. |
| R1-F10 | P2 | **CLOSED** | `"""Select the row from bil_invoices when syncing."""` → PASS 0. Docstring positions excluded by node `id()` (not by string value), counted, and the `__doc__` residual disclosed as an uncovered gap rather than claimed covered — the correction ADR-011's Follow-up explicitly demanded. |
| R1-F11 | P2 | **CLOSED** | `b'SELECT a FROM bil_invoices'` → FAIL 1. D6.4's exclusion is correctly *not* extended to `bytes`, with the reason stated. |
| R1-F12 | P2 | **CLOSED (relocation, correctly labeled)** | (i) PASS over a trivial tree now discloses "0 text subject(s)" recognised, so a vacuous PASS is self-evidencing; ADR-011 requires this be labeled a relocation, and the evidence set does label it. (ii) Prefix floor executed as decided: `["a"]`, `["ab"]`, `["a_"]` all ERROR; `["ab_"]` accepted. The ERROR message reads the pattern off the applied regex rather than restating it — a genuinely good hardening. |
| R1-F13 | P2 | **CLOSED** | `app.modules.membership.nope` → ERROR, "does not resolve to an existing module file or package … a typo must narrow the approved surface, never widen it". The `os.lstat` component walk refuses a symlink anywhere on the path; `Path.exists()`/`is_file()` are correctly avoided per D5.4. |
| R1-F14 | P2 | **CLOSED at code/test level — evidence caveat (see R2-N06)** | `test_scn007_raw_table_reference_is_denied_cross_domain_and_clean_for_own_table` exists and passes; it is a genuine matched negative/positive pair whose only cross-module signal is the table identifier itself, which is exactly what round 1 asked for. `GATE2-R1-F14-RAW-TABLE-CLI-CAPTURE-2026-10-06.json` exists and its two cases reproduce under my own runs. Caveat: that capture records source SHA `fc6404c6…`, not the reviewed snapshot. |

### Untracked P3s (R1-F15..F21)

| # | Disposition | Independent evidence |
|---|---|---|
| R1-F15 | **CLOSED at the producer; the rule it motivated is not implemented** | The f-string double-report is gone (1 row, was 2). But identical rows are still not deduplicated in general — see R2-N03. |
| R1-F16 | **OPEN** | The docstring sentence is byte-unchanged: "any import FROM `_shared` INTO a domain module is `CROSS_DOMAIN_SQL_IMPORT`". Behaviour is the opposite and is correct — a domain module importing `_shared` → PASS 0; `_shared` importing a module's interface → `CROSS_DOMAIN_SQL_IMPORT: _shared -> membership`, FAIL 1. ADR-011 D4 states in terms that this sentence "must be corrected". It was not. |
| R1-F17 | **OPEN (unchanged, cosmetic)** | `…/modules/` → PASS 0; `…/modules/.` → PASS 0; `…/app/modules/../modules` → ERROR 2. Fails closed; a `Path.resolve()` would still avoid a misleading diagnostic on a semantically identical path. |
| R1-F18 | **CLOSED by relocation** | A violation in `membership/.hidden/v.py` is still invisible (PASS 0), but a pruned dot-directory is now an explicit ADR-011 D5.1 bucket, counted **by reason** in the D8 file-accounting note, whose RESIDUAL paragraph states that a pruned directory's contents are not counted at any depth. Disclosed rather than silent — which is what the finding asked for. |
| R1-F19 | **OPEN — an unmet ADR-011 Follow-up directive** | No root `ruff.toml`, `.ruff.toml` or `pyproject.toml` exists. `ruff check` on both targets → "All checks passed!", still against ruff's built-in defaults. `--select E501` now reports **881 errors** (round 1 measured 299). ADR-011's Follow-up instructed the implementer to "pin a root `ruff.toml`, re-run, and record the figure measured under the pinned config". That was not done, and the 582-error drift between the two unpinned measurements is the direct demonstration of why it matters. |
| R1-F20 | **PARTIALLY OPEN** | Deterministic across runs (3/3 identical orderings) ✓. Still reverse-lexicographic: `top.py, sub3, sub2, sub1, sub0`. Not ordered by `(code, subject, detail)` as D7.4 requires — folded into R2-N03. |
| R1-F21 | **PARTIALLY CLOSED** | Quoted identifiers are now extracted and attributed (`FROM "bil_invoices"` → FAIL 1), which was the substantive half; the explicit character-by-character lexer handling `""` escapes is a real improvement over the rejected regex alternation. Inline SQL comments still ERROR (`FROM /*x*/ bil_invoices` → 2). Fails closed. |

## 5. New findings

### R2-N01 · **P0** · A cross-domain raw-table reference PASSes, exit 0, whenever any other identifier in the same statement extracts cleanly

**Evidence:** `tools/validate_architecture_gates.py:2674` (extractor keyword
set), `:2821-2835` (`_extract_table_identifiers` — one identifier per
keyword match), `:3261-3289` (the I-1 backstop, guarded by `if not idents:`).

```python
_TABLE_KEYWORD_RE = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\b", re.IGNORECASE)
...
def _extract_table_identifiers(text):
    idents = []
    for kw in _TABLE_KEYWORD_RE.finditer(text):
        found = _identifier_after_keyword(text, kw.end())   # ONE identifier per keyword
        if found is not None:
            idents.append(found[0])
    return idents
...
    idents = _extract_table_identifiers(text)
    if not idents:                      # <-- backstop only when NOTHING extracted
        if _implies_table_position(text):
            ... ERROR
```

Two layers are each individually sound and jointly fail open. The extractor
recognises one identifier per keyword occurrence, so a comma-separated table
list, a `REFERENCES` clause, and a `USING` clause are table positions it
never visits. The backstop is scoped to the statement, not to the table
position, so it is disarmed by the first identifier that *does* extract.

**Reproducer** (fixture: `membership` owns `mem_`/COM-01, `billing` owns
`bil_`/COM-03, `default_schema: "public"`, no cross-module Python import;
the string is the sole content of `membership/q.py`):

```
backend/.venv/bin/python tools/validate_architecture_gates.py --gate module-deps \
  --modules-dir /tmp/g2r2/fx/app/modules --module-manifest /tmp/g2r2/mf/ownership.json

  'SELECT a FROM mem_roster JOIN bil_invoices ON 1=1'   exit=1 FAIL  (control)
  'SELECT a FROM bil_invoices'                          exit=1 FAIL  (control)
  'SELECT a FROM mem_roster, bil_invoices'              exit=0 PASS  <-- P0
  'CREATE TABLE mem_t (c int REFERENCES bil_invoices)'  exit=0 PASS  <-- P0
  'DELETE FROM mem_roster USING bil_invoices'           exit=0 PASS  <-- P0
  'SELECT a FROM mem_roster, bil_invoices, bil_ledger'  exit=0 PASS  <-- P0 (2 missed)
  'SELECT a FROM mem_roster, ONLY bil_invoices'         exit=0 PASS  <-- P0
```

Identical through a `.sql` file (`membership/r.sql` containing
`SELECT a FROM mem_roster, bil_invoices;`) → exit 0.

**The disclosure makes it worse, not better.** On the comma-list PASS the
D8 note reads:

```
ADR-011 D8 table-reference attribution: 1 table-position identifier reference(s)
extracted and attributed -- own (D3.2 state 1) 1, another module's (state 2, FAIL
CROSS_DOMAIN_SQL_IMPORT) 0, ... ; the counts are complete for this run.
```

A second table-position identifier was present in the scanned text and was
never extracted, so "complete for this run" is substantively false on
precisely the dimension D8 exists to make trustworthy. The note's RESIDUAL
paragraph enumerates what is not examined — docstrings, undecodable bytes,
D7.1 dynamic constructs, out-of-tree text — and this shape is in none of
those classes: the identifier is a plain literal in fully static text the
scanner did receive and did examine.

**Why it matters against the governing decisions.** ADR-011 **D3.2** states
"Every identifier in a table position resolves to exactly one of six
states"; here one resolves to none. **D8** requires a PASS to be
self-evidencing; this PASS asserts completeness it does not have. **D9**
rejects "'Unowned ⇒ benign note', in any form", and the stated point of
"in any form" is that the prohibited thing is the effect — an unexamined
owned table reaching a clean verdict is that effect without even a note.
TSD **§24.1** makes "cross-domain raw SQL/ORM imports fail CI" the gate's
headline invariant and **§6.3** rejects "direct repository/table coupling"
specifically — a foreign key to another module's table is the textbook
instance, and it PASSes. **SCN-MOD001-007**'s acceptance text is a
cross-domain raw-table reference; its denial is not reliable.

The code's own comment at `:2678-2682` states the intent this defect
defeats: the backstop's keyword set is "deliberately the full
`_TABLE_POSITION_KEYWORDS` set … independent of what the extractor above
can actually resolve into an identifier: **a keyword the extractor cannot
yet resolve must still fail closed via the backstop below, never pass
silently**." That property holds only for statements with zero extracted
identifiers. The comment asserts it unconditionally.

**Not covered by the B HOLD.** This is independent of CTE state 3. It is
reachable today with `cte_names` empty, it is a false *clean* rather than
the false *fail* the B HOLD accepted, and no part of the U1/U2 redecision,
the D8 coverage-gap disclosure, or the coverage note's "the rest of the SQL
lexer rework remain unimplemented" names it. Remediation does not require
touching state 3 in any direction.

**Untested.** No test asserts attribution over a comma-separated table list
or a `REFERENCES`/`USING` table position. The shape `SELECT * FROM a, b`
does appear in the corpus — at `test_validate_architecture_gates.py:3785`,
`:3967`, `:3977`, `:4024`, `:4119`, `:4938` — but only inside `_cte_scopes`
/ `_collect_cte_names` pure-helper tests, i.e. exercised solely by the
helper the B HOLD forbids wiring, and never as an extraction or attribution
assertion. The 466 passing tests are informative about what they cover;
they do not reach this surface.

### R2-N02 · **P1** · Finding against ADR-011: D6 never requires extraction totality, which D3.2 presupposes

ADR-011's Follow-up directs the round-2 reviewer to "judge whether this ADR
itself has a gap — if so, report it as a finding against ADR-011." This is
that finding.

D6.1 fixes the **trigger** as a deliberate over-approximation and argues
correctly that widening it "can only ever yield strictly more ERRORs". D6.3
fixes the **zero-identifier backstop**. Neither D6 nor any other clause
constrains the **extractor** — which table positions must yield an
identifier. D3.2's opening sentence ("Every identifier in a table position
resolves to exactly one of six states") and D8's self-evidencing
requirement both presuppose extraction totality that the ADR never
mandates, and D7.1's discriminator ("whether an identifier was actually
extracted") makes a silently-unextracted identifier indistinguishable from
one that was never there.

The consequence is that an implementation can satisfy D1-D8 literally and
still produce R2-N01. The gap is in the contract, not only in the code, so
a code-only fix would close the instance while leaving the class
unconstrained — the exact failure mode ADR-011's own "Alternatives
considered" table rejected when it declined to merely widen the regexes.
This belongs to `veyro-lead` to amend; this review proposes no specific
amendment text.

### R2-N03 · **P2** · ADR-011 D7.4 is implemented only for the coverage code; the main violation lists are neither deduplicated nor ordered by `(code, subject, detail)`

**Evidence:** `_dedupe_coverage_violations` (`:2336-2347`) is the only
implementation, and its own docstring scopes itself: "D7.4-**style**
discipline applied to this gate's **own coverage ERROR code**". No
equivalent is applied to `violations`, `uninspectable` or `unattributed`
in `run_module_deps_gate` (`:5861-5863`, assembled through `:6024`).

```
'SELECT a FROM bil_invoices JOIN bil_invoices ON 1=1'
  -> 2 identical rows, same (code, subject, detail):
     CROSS_DOMAIN_SQL_IMPORT: membership -> billing — membership/q.py:1: table 'bil_invoices' owned by 'billing'

'SELECT a FROM bil_zeta' then 'SELECT a FROM bil_alpha' in one file
  -> emitted bil_zeta, bil_alpha  (source order, not sorted by subject/detail)

violations across subdirectories
  -> top.py, sub3, sub2, sub1, sub0  (reverse-lexicographic, deterministic across 3 runs)
```

D7.4 reads: "Violations are deduplicated and deterministically ordered by
`(code, subject, detail)`, first-seen order preserved within a key
(R1-F15, R1-F20)." Deterministic ✓. Deduplicated and ordered by that key ✗.
R1-F15's specific duplicate was fixed at its producer instead, so the rule
it was cited to motivate was never built; R1-F20 is therefore still open.
Fails closed (counts inflate, never deflate), hence P2 — but a reader
cannot currently take a violation count at face value, and `--json`
consumers diffing CI output get churn `_finish`'s own `sorted(checked)`
does not.

### R2-N04 · **P2** · The module docstring — the gate's only stated contract for a reader — is materially stale and self-contradictory, and the stale text asserts exactly the behaviour ADR-011 D9 prohibits

**Evidence:** `tools/validate_architecture_gates.py:249-257`:

> "SQL check: a string … is SQL-ish if it contains … one of
> SELECT/INSERT/UPDATE/DELETE/TRUNCATE **and** one of FROM/INTO/JOIN/TABLE/SET.
> … **An identifier no module owns is not flagged — only counted and
> disclosed in a note**, since flagging it would false-FAIL on CTEs, aliases
> and catalog tables."

Both sentences are false of the implementation. The trigger is now the
20-verb `_TRIGGER_VERBS` set with no clause-keyword requirement (D6.1), and
an unowned identifier is `MODULE_DEPS_TABLE_UNATTRIBUTED` ERROR at exit 2
(D3.2 state 6) — confirmed by execution throughout §4. The stale sentence
is a verbatim statement of the "unowned ⇒ benign note" terminal state that
**ADR-011 D9 rejects "in any form"** and that the ADR identifies as the
root of R1-F01. It is also the sentence a reader would most reasonably rely
on when judging whether a PASS means anything.

Compounding, in the same file:

- `:304-305` — "Unlike gates 1 (RLS) and 4 (permission), this gate's input
  contract is not yet fixed by an ADR." Contradicted by ADR-011 and by this
  file's own section header at `:1446` ("input contract fixed by ADR-011").
- `:289-293` — restates the same "not attributed to anyone" framing.
- `:205-207` — the R1-F16 `_shared` inversion ADR-011 D4 required corrected.
- `:1677-1679` — inline comment says `default_schema` is "Not yet threaded
  into any resolution logic (that is D3.3, out of scope here)", contradicted
  by `parse_module_manifest`'s own docstring 20 lines above and by the live
  stripping at `:3024`.
- `:1727-1730` — inline comment says the D3.5 ownership cross-check "is
  deferred", contradicted by its implementation at `:1858-1866`.

Each is a documentation defect rather than a behavioural one, which is why
this is P2 and not higher. Collectively they matter more than the sum: the
docstring and the runtime notes now disagree about the gate's terminal
states, and under **DC-12** a correct implementation whose stated contract
asserts the prohibited behaviour is not finished work. The `:249-257`
paragraph in particular would let a future session "restore" a documented
behaviour that ADR-011 forbids.

### R2-N05 · **P3** · Seven recorded round-1 findings are outside the tracked finding set

`GATE2-R1-F01-R2-READINESS-RECONCILIATION-2026-10-06.md` states that "the
live R04 finding projection lists **all 14** original R1 findings as
`VERIFIED_NOT_RECONCILED`, formally `OPEN`", and concludes "no outstanding
original R1 code/test increment is identified by the current 14-finding
projection". The round-1 report records **21** findings (P3=7). R1-F15..F21
are therefore not in the projection, and three of them are genuinely open
(R1-F16, R1-F17, R1-F19) with R1-F20 partially open — including one,
R1-F19, that is an explicit unmet ADR-011 Follow-up directive.

This is the shape **DC-08** was written against ("a defect that only exists
as narrative text does not show up in an 'open bugs' count and creates a
false-clean gate"), and the readiness conclusion is narrower than it reads
because of it. Recorded as a tracking defect, not a code defect; it needs a
projection reconciliation rather than an implementation increment.

### R2-N06 · **P3** · The R1-F14 evidence set is internally inconsistent about whether its capture exists and which snapshot it describes

`GATE2-R1-F14-SOFT-STOP-RECONCILIATION-2026-10-06.md` states that the
worker "did not persist the dedicated raw-table test or the requested
output-capture evidence file", that "the requested evidence file is
absent", and that "the source SHA-256 remains `fc6404c6…`". Both artifacts
now exist: the test is at `test_validate_architecture_gates.py:1360` and
passes, and `GATE2-R1-F14-RAW-TABLE-CLI-CAPTURE-2026-10-06.json` is
present — but that capture records `sourceSha256: fc6404c6…`, not the
reviewed snapshot `b9e012a4…`. The substance reproduces under my own runs
on the current snapshot, so this is an evidence-currency and
record-consistency defect, not a misrepresentation of behaviour. A reader
reconciling these two files in sequence would reach the wrong conclusion
about what exists.

## 6. The U1/U2 B HOLD and the D8 state-3 disclosure — assessment only

Per dispatch, I neither requested nor designed live state-3 wiring. I
verified the *facts* the B HOLD rests on and the honesty of its disclosure:

- **State 3 is genuinely unreachable live.** `_scan_sql_statement:3298`
  calls `attribute_table_identifier(ident, modules, importer,
  default_schema)` with four arguments against the
  `cte_names: frozenset[str] = frozenset()` default (`:2995`). Confirmed in
  source and by the runtime note reporting "CTE-local (state 3) 0".
- **The CTE-first precedence the redecision found is real.**
  `_attribute_bare_identifier:2973` tests `if name in cte_names:` ahead of
  the `pg_` check and ahead of `_owner_by_prefix`. The redecision's §2.1
  characterisation is accurate.
- **The disclosure is honest and correctly scoped.** The D8 table-reference
  note labels the state-3 zero a LIMIT — "structurally unreachable on this
  path and its count is therefore a genuine zero that records an
  unimplemented path, **NOT** an observation that no CTE-bound reference
  occurred" — and states that a `WITH`-bound name in table position is
  counted unattributed/ERROR instead. That is the false-*fail* divergence
  the B HOLD accepted, described without overstatement. `ref_counts.cte` is
  not wired to look exercised; the inline comment at `:3321-3325` says so.

**Implication I am obliged to record:** the B HOLD is reasoned over the
CTE lane in isolation, and its §4 "smallest next legal action" directs the
effort back to "the oldest highest-severity still-open round-1 finding".
R2-N01 shows the gate has a live false-*clean* path that is independent of
state 3 and was not in view when that priority was set. The B HOLD remains
correct on its own question — I am not reopening it — but the premise that
the scanner's current state is "maximally fail-closed" (§4) does not hold.
That is a finding about the scanner, not about the hold.

## 7. Commands run and results

Everything below I executed from `/Users/ahmadmabrouk/Desktop/Veyro`.
Where I only read code, §4 and §5 say so.

**Baseline reproduction**

```
shasum -a 256 tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
   -> b9e012a47a10935fc5dd390383b6907131c65be01372b5b02dc6d0b47e8e6484  (match)
   -> 83779ff7c49626be57200374024f4b262879d86291b4d3b116581c4b38ac0288  (match)

backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q   -> 466 passed in 3.91s
backend/.venv/bin/python -m pytest tools/tests/ -q                                      -> 539 passed in 4.64s
backend/.venv/bin/ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py
                                                                                        -> All checks passed!
backend/.venv/bin/ruff check --select E501 <both>                                       -> Found 881 errors.
backend/.venv/bin/python -m pytest ... -k raw_table                                     -> 1 passed, 465 deselected
```

All claimed baselines reproduce. See R1-F19 for what "Ruff clean" does and
does not mean here, and note the 299 → 881 drift against round 1.

**Adversarial probes.** One synthetic two-module fixture under
`/tmp/g2r2/fx` (`membership`/COM-01/`mem_`, `billing`/COM-03/`bil_` — a
real §6.3 pair, so the pair checks are exercised on the same tree) plus
manifest variants under `/tmp/g2r2/mf`. The gate was invoked as a
subprocess with explicit `--modules-dir`/`--module-manifest` on every run.
No network, no paid service, no real member data, no tracked file touched.

| Probe family | Cases | Established |
|---|---|---|
| Identifier spelling / qualification / case | 7 | R1-F01 closed; `"BIL_INVOICES"` correctly a distinct table |
| DDL / MERGE / COPY / LOCK / GRANT | 8 | R1-F02 closed; 8/8 non-zero |
| Extraction-position coverage | 7 | **R2-N01 (P0)**, `.py` literal and `.sql` file |
| Dynamic-import idioms | 7 | R1-F05 closed |
| Assembled SQL | 5 | R1-F06 closed |
| Coverage: modules-root, namespace pkg, dot-dir | 3 | R1-F03/F04 closed; R1-F18 relocated |
| Output contract: non-UTF-8, `--json`, D7.3 funnel | 4 | R1-F07 closed; funnel verified by in-process fault injection |
| Manifest schema and D9 bypass attempts | 13 | R1-F08/F12/F13 closed; every bypass refused; Verdict C's 3 cases re-asserted |
| D7.4 dedup / ordering | 3 | **R2-N03** |
| §6.3 pair enforcement | 3 | permitted PASS, reverse `REVERSE_EDGE_NOT_EVENT_DRIVEN`, reverse-via-internals correctly `CROSS_DOMAIN_SQL_IMPORT` (precedence as documented) |
| Docstring prose / `_shared` direction | 3 | R1-F10 closed; **R1-F16 open** |
| `--modules-dir` normalization | 3 | R1-F17 open |

`BIDIRECTIONAL_PAIRS` (`:1451-1456`) was diffed against `TSD_MIRROR.md`
§6.3 (`:1527`, `:1539`, `:1550`, `:1560`): COM-01→COM-03, REL-01→DAT-01,
GRO-01→ENG-01, LIF-01→GOV-04 — exact match, pinned in source, not
manifest-configurable, as D6.6 requires.

**Read, not executed:** ADR-011 in full; the round-1 report in full;
`GATE2-R1-D6-U1-U2-QUALIFIED-REDECISION-2026-10-05.md`;
`GATE2-R1-D6-D8-COVERAGE-GAP-2026-10-05.md`;
`GATE2-R1-F01-R2-READINESS-RECONCILIATION-2026-10-06.md`;
`GATE2-R1-F14-SOFT-STOP-RECONCILIATION-2026-10-06.md`;
`GATE2-R1-F12-D8-POSITIVE-EVIDENCE-SET-RECONCILIATION-2026-10-06.md`;
`GATE2-R1-F14-RAW-TABLE-CLI-CAPTURE-2026-10-06.json`; `PROJECT_INDEX.md`;
`DEVELOPMENT_CONSTITUTION.md`; `MODEL_ROUTING.md`; `SESSION_BOOTSTRAP.md`;
`REVIEW_IN_FLIGHT.md`; `SCENARIOS.md` lines 405-412; `TSD_MIRROR.md` §6.3.

## 8. Scenario mapping — code assurance only, no promotion

I promote nothing and sign off nothing. SCN-MOD001-006/-007/-095/-096
remain **NOT EXECUTED** and unpromoted.

| Scenario | Criterion | Code assurance |
|---|---|---|
| **SCN-MOD001-006** — own prefix / approved interface → PASS | positive path PASSes | **Supported.** Reproduced PASS exit 0 on own-table SQL and on the permitted §6.3 edge. R1-F12's caveat is closed: a PASS now discloses recognised-subject, table-state and import-edge counters, so a vacuous PASS is distinguishable from an evidenced one. |
| **SCN-MOD001-007** — another module's raw table / ORM model → `CROSS_DOMAIN_SQL_IMPORT` citing both modules | ORM-model / internal-import half | **Supported.** `CROSS_DOMAIN_SQL_IMPORT: billing -> membership — 'billing' (domain COM-03) imports 'membership' (domain COM-01) internal path … at billing/q.py:1`. Both modules, both domains, resolved path and `relpath:lineno` present; takes precedence over the pair check in both directions. |
| | raw-table half | **NOT supported as a reliable denial.** Bare, qualified, cased and quoted spellings now all deny correctly (R1-F01 closed) and a dedicated matched-pair test exists (R1-F14). But **R2-N01**: the same violation in a comma-separated `FROM` list, a `REFERENCES` clause or a `USING` clause returns PASS exit 0 with a report asserting complete counts. **This is the reason the verdict is BLOCKED.** |
| **SCN-MOD001-095** — one §6.3 pair, permitted direction → PASS | permitted direction PASSes | **Supported.** Verified on the COM-01→COM-03 pair; all four pairs match the TSD mirror exactly. |
| **SCN-MOD001-096** — same pair, reverse direction → `REVERSE_EDGE_NOT_EVENT_DRIVEN` | reverse denied, citing permitted direction | **Supported.** `REVERSE_EDGE_NOT_EVENT_DRIVEN: billing -> membership — … TSD §6.3 permits only COM-01 -> COM-03 synchronously, the reverse edge must remain event-driven.` |

**Verdict C / Verdict D compliance.** Verdict C's three cases re-asserted
unchanged under execution: same-module nesting (`["mem_", "mem_event_"]`)
accepted, cross-module overlap (`mem_` vs `mem_x_`) ERROR with no exception
path, exact duplicate ERROR as malformed input. Verdict A's premise holds —
no `contracts/modules/ownership.json` exists, none was created, and no
probe reached the real tree. Verdict A.4's premise is still moot: no
`.github/workflows/` and no committed CI configuration exist. **No instance
found of the implementation exceeding, contradicting or silently narrowing
ADR-011 or any Verdict**, except the D7.4 shortfall in R2-N03 and the
docstring assertions in R2-N04.

## 9. Limitations and scope caveats

- **Both targets are untracked WIP**, so nothing could be diffed against a
  committed state. NEW-vs-RECURRING is established from the round-1 report
  and the 14-finding projection, not from version history.
- **Real-tree behaviour is unverifiable by design.** No manifest exists
  (owner-blocked under Verdict A), so every functional probe is
  fixture-scoped. R2-N01's practical reach is therefore the same as
  R1-F01's was: it blocks the reliability of SCN-MOD001-007's denial, and
  it would become live the moment a manifest is authored. It is not a
  current real-tree exposure, and gate 2 is not a security boundary (D8).
- **Case behaviour is filesystem-specific.** All probing ran on
  case-insensitive APFS; behaviour on a case-sensitive Linux CI filesystem
  was not tested and is expected to be stricter, not looser.
- **Fixture containment** was established by code reading plus the absence
  of a real manifest, not by syscall tracing. No `dtruss`/`fs_usage` run.
- **D7.3's funnel was verified by in-process fault injection** (patching
  `_discover_modules` on an imported copy of the module), not by finding a
  naturally reachable unexpected exception. No file was modified to do this.
- **The B HOLD was treated as binding input, never as approval** (DC-14).
  ADR-011 likewise is an input to this review, not an approval of it.
- **Severity assignments are mine.** R2-N02's P1 is arguable — it is a
  contract gap with no independent runtime consequence beyond R2-N01, and a
  reader who regards ADR amendment as implied by R2-N01's fix could rate it
  P2. The case for P1 is that a code-only fix closes the instance and
  leaves the class unconstrained.
- **Not re-verified:** TSD Appendix I / DOM-001; ADR-009 / ADR-010 contents;
  EIP §4.3; the `_cte_scopes` lexer helpers' nesting/tag-matching logic
  against PostgreSQL semantics (out of scope under the B HOLD, and I did
  not treat the U1 tests' comments as verified facts).
- **No remediation attempted and no fix written.** Routing of these
  findings is the lead's call, not this review's.

## 10. Model / session proof and independence

- **Model identity:** Opus 5 (1M context), exact model ID
  `claude-opus-5[1m]`, as reported by this environment. No `mr_verify.py`
  attestation was run against this dispatch's own transcript —
  self-attestation is of little value and the tool is the orchestrating
  session's to run; stated rather than omitted. If an attestation is wanted
  for the record, the orchestrator should attest this transcript.
- **Session/run identity:** this review honored the pre-written
  `REVIEW_IN_FLIGHT.md` claim naming runner operation
  `bcd46b31-b6a1-4fe5-8f26-3160e2ac45b5`. No separate subagent id was
  issued — this dispatch was executed in a single fresh independent
  reviewer context.
- **Independence:** fresh, independent context. I did not author, edit or
  advise on `tools/validate_architecture_gates.py`, its tests, ADR-011, any
  gate-2 implementation or decision record, or the round-1 review. ADR-011
  and the B HOLD were treated as binding input; every implementation and
  evidence record was treated as a claim to verify, and §4's dispositions
  rest on my own execution rather than on those claims. No message from any
  agent was treated as approval or consent.
- **Owner-reserved restrictions observed:** no paid service, no spend, no
  real member data (synthetic fixtures only), no deploy or production
  action, no material product/pricing/business/architecture/scope change.
- **No writes outside this file.** No source, test, ADR, scenario catalog,
  bug registry, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md` or
  `REVIEW_IN_FLIGHT.md` edit; no `git add`, commit, stage or push; no
  `graphify update`. All probe artifacts live under `/tmp/g2r2/`, outside
  the repository. Snapshot hashes re-verified after all probing and still
  match (§2).

## 11. Reviewer's recommended routing — not a decision

- **R2-N01 (P0)** must be adjudicated before SCN-MOD001-006/-007/-095/-096
  go to scenario review. It bears directly on whether SCN-MOD001-007's
  denial is reliable, and it is a silent exit-0 pass on the gate's headline
  invariant. Note for whoever scopes the fix: widening
  `_TABLE_KEYWORD_RE` would move this instance without addressing the
  class, which is the shape ADR-011's "Alternatives considered" table
  already rejected once — the structural question is whether the backstop
  should be scoped to the table position rather than to the statement.
  That is a contract call, not an implementation detail, which is why
  R2-N02 is routed with it.
- **R2-N02 (P1)** routes to `veyro-lead` as an ADR-011 amendment question,
  jointly with R2-N01.
- **R2-N03 / R2-N04 (P2)** are self-contained and need no new contract.
  R2-N04's `:249-257` paragraph is the one I would not leave standing in
  any case: it documents, as current behaviour, the exact terminal state
  ADR-011 D9 forbids.
- **R2-N05 (P3)** needs a projection reconciliation so that R1-F16, F17,
  F19 and F20 are tracked rather than carried as narrative. **R1-F19** in
  particular is an unmet ADR-011 Follow-up directive, not a new request.
- **Round counters:** this unit's completed-round count becomes **2**.
  SCN-MOD001-070 (5) and DOM-002 (4) are unrelated historical counters and
  were not reset, reused, or touched.

**No scenario PASS, no promotion, no module certification is claimed or
implied by this document.** MOD-001 remains uncertified; WIP=1 holds and
MOD-002 stays locked.

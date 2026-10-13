# D6 pre-wiring T1–T9 sequencing — named lead decision (2026-10-05)

**Recovery provenance:** The guarded inspection `f5e710ea-0b6c-484a-97f7-afc278568730` stopped at the 480-second soft-no-progress budget (exit 42) while the top-level transport was preparing this file. This is **not** a failed test or review verdict. The foreground named `veyro-lead` Task had completed before that stop; its actual sidechain transcript is `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/6759b82a-f049-452e-837d-d7851c5c4883/subagents/agent-aa79ee7be399c928f.jsonl` (agent `aa79ee7be399c928f`). The orchestrator independently ran `mr_verify.py` with `opus veyro-lead`: **PASS 44/44 `claude-opus-5`**. Source and test hashes were unchanged at recovery (`3e05a5108061cd1bf56a27a6e9d1896df3793ec6b9df919664a7cd692d16ed5d`, `89c3b9853dd3f809918d26fc4f6b71f6bed401f502f76f33de9e57e8391e6bdc`). No code, test, or scenario verdict was produced by this operation. Report salvaged from the completed child conclusion at 2026-10-05T07:52:25.649405+00:00; the ACPX wrapper remains correctly recorded as SOFT_NO_PROGRESS.

**Operational disposition:** accept the bounded named-lead clarification as recovered evidence, not as a completed guarded operation, independent review, scenario PASS, or live-wiring authorization. The child conclusion follows verbatim.

---

## BOUNDED CONCLUSION — GATE2-R1-D6 T1–T9 sequencing adjudication (named `veyro-lead`, read-only, 2026-10-05)

The contradiction is real but resolvable without owner input or a baseline re-read, and it resolves **against** the literal "land T1–T9 then adjudicate" wording while **preserving that instruction's intent**. The prior lead's ordering is **AMENDED, not superseded**: T1–T9 is not one landable unit. Five of the nine (T1, T5, T7, T8, T9) are pure assertions on `_cte_scopes` and are landable green today — I verified each of their stated propositions by directly executing the current helper, including I-5 extraction equivalence (0 divergences) and T9's subset property (0 violations, non-vacuity control satisfiable). Four (T2, T3, T4, T6) are live `run_module_deps_gate` tests. Of those, T3 and T6 **cannot** be green before wiring by construction — both assert a `PASS` that requires D3.2 state 3 to be reachable, and I confirmed by direct code reading that `_scan_sql_text` (`tools/validate_architecture_gates.py:2188-2203`) still calls `attribute_table_identifier(ident, modules, importer, default_schema)` with no `cte_names` argument, so state 3 is unreachable live. T2 and T4 would pass today but **vacuously**, for a reason unrelated to the feature under test. ADR-011 D3.2/D9 risk adjudication not only *may* occur before live-gate green — it **must**, because the question it adjudicates is precisely *whether state 3 may be made reachable at all*, and live green presupposes the answer. The corrected ordering is therefore: pure-subset tests → seeded property corpus → fresh ADR-011 D3.2/D9 adjudication → (only if permitted) wiring increment carrying T2/T3/T4/T6 as its own both-directions acceptance set. The open BLOCKED round-1 code review does **not** independently block further pure-test authoring and is **not** the smallest next subgoal: its P0 (R1-F01) is an adjudicated-and-implemented finding, and what remains open is the *verdict*, clearable only by a fresh independent round-2 review — which gates **scenario promotion**, not increment authoring.

---

### (a) Per-test disposition, T1 through T9

| Test | Kind | Disposition | One-line basis (source-cited) |
|---|---|---|---|
| **T1** `test_cte_binding_is_not_visible_to_a_later_statement` | pure | **LANDABLE-GREEN-NOW** | Decision §6 T1 asserts three inputs on `_cte_scopes`; I executed all three against the current helper: `[['bil_scratch'],[]]`, `[['a','b'],[]]`, and `WITH RECURSIVE` → `[[],[]]` ("assert **both** scopes are empty — `RECURSIVE` fails closed rather than binding"). T1a/T1b content already exists under other names in the repo; **T1c (RECURSIVE) is absent** from the `_cte_scopes` section. |
| **T2** `test_live_same_named_table_in_second_statement_is_not_suppressed` | live, shape (a) | **LANDABLE-GREEN-NOW — but vacuous** | Pre-wiring, `cte_names` is the empty default, so **both** `bil_scratch` references resolve by `_owner_by_prefix` to `billing` → `CROSS_DOMAIN_SQL_IMPORT`, `FAIL`. T2's assertions hold identically before and after wiring, so it discriminates nothing. Decision §6 preamble concedes this: "tests 3 and 6's controls are what make the others non-vacuous." |
| **T3** `test_live_single_statement_cte_reference_is_clean_control` | live, shape (a) | **LIVE-GATE-RED / DEFERRED** | Its own wording: "**If this test does not currently FAIL before the wiring lands and PASS after, the wiring is not actually live** — it must be run in both directions and the result recorded." It asserts `report.status == PASS` for a lone `WITH bil_scratch …` statement; with state 3 unreachable that is a `FAIL`. See (b). |
| **T4** `test_live_python_string_literal_cte_scope_is_statement_scoped` | live, shape (b) | **LANDABLE-GREEN-NOW — but vacuous** | Same mechanism as T2 (empty `cte_names` ⇒ `bil_scratch` is a prefix hit for `billing`). Its third assertion — the `queries.py:<lineno>` `loc` form — exercises pre-existing wired behaviour and does not depend on state 3 either. |
| **T5** `test_semicolon_inside_quoted_string_declines_only_its_own_statement` | pure | **LANDABLE-GREEN-NOW** | Executed: 2 scopes, `[[], ['c']]`, and neither scope's text equals the whole input — the hidden `;` produced no cut and the decline is statement-local. Equivalent coverage already exists as `test_cte_scopes_semicolon_inside_single_quoted_literal_declines_only_its_own_statement`. |
| **T6** `test_semicolon_inside_line_comment_declines_binding_fail_closed` | live + control, shape (a) | **LIVE-GATE-RED / DEFERRED** (as one test function) | Its primary half (`ERROR`, `MODULE_DEPS_TABLE_UNATTRIBUTED` naming `scratch_cte`) is green now but vacuously — `_md_base_modules()` declares only `membership`/`membership_` (`tools/tests/test_validate_architecture_gates.py:1220-1222`), so `scratch_cte` is unattributed with or without a binding mechanism. Its **control** half — "the identical file with the semicolon removed from the comment … must return `PASS` with no violations" — requires state 3 live; pre-wiring that variant is `ERROR`. The function as specified therefore cannot pass today. |
| **T7** `test_dollar_quoted_body_semicolon_is_not_a_statement_cut` | pure | **LANDABLE-GREEN-NOW** | Executed both the `$$` and `$tag$` forms: 2 scopes each, `scopes[0][1] == frozenset()`. Equivalent coverage already exists as `test_cte_scopes_semicolon_inside_dollar_quoted_body_is_not_a_statement_cut` (+ tagged variant). |
| **T8** `test_extraction_equivalence_and_unlexable_decline` | pure | **LANDABLE-GREEN-NOW — absent from the repo** | Executed I-5 over the T1/T5/T7 inputs plus `"SELECT * FROM t WHERE x = 'unterminated"` and the backslash-escape shape: **0 divergences** between `Counter(⋃ _extract_table_identifiers(seg))` and `Counter(_extract_table_identifiers(T))`; the unterminated input yields exactly one scope with an empty set; the escape input yields **no** `fake` binding. No `_extract_table_identifiers` assertion exists anywhere in the `_cte_scopes` test section. |
| **T9** `test_segment_bindings_are_a_subset_of_whole_text_bindings` | pure | **LANDABLE-GREEN-NOW — absent from the repo** | Executed `N(s) <= _collect_cte_names(T)` over an 11-input corpus: **0 violations**; non-vacuity control satisfiable (4 scopes with non-empty `N(s)`; 5 scopes where the whole-text set is strictly larger). Correction §5 calls it "the single most important test added by this correction." **Note:** T9 is *more* necessary under the one-pass design, not less — the one-pass `_cte_scopes` has `WITH`-jump / `;`-cut / depth interactions that whole-text `_collect_cte_names` does not, so T9 remains a genuine two-walk comparator lock even though Lemma L was made vacuous *for segmentation*. |

**T10 (out of the dispatch's T1–T9 range, recorded for completeness):** correction §5's structural Lemma-L guard, and M5, are **obsolete by construction**. `_split_sql_statements` does not exist in the source; the lead qualification §2(b)(1) anticipated exactly this ("T10/M5 become unnecessary rather than under-scoped"). A future session must not carry T10 forward as an outstanding obligation.

---

### (b) The T3 question specifically

T3's clause is, verbatim from `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-D6-CTE-STATEMENT-SCOPE-DECISION-2026-10-05.md` §6:

> "**If this test does not currently FAIL before the wiring lands and PASS after, the wiring is not actually live** — it must be run in both directions and the result recorded."

Read without softening: this is a **directional-proof obligation on the wiring increment**, not an instruction to commit a red test now. T3 is a two-sided artifact; its "after" half is only observable once `_scan_sql_text` is wired, so **no reading makes T3 satisfiable against the pure helper**. Against the three options posed:

- **(i) Currently unlandable as a green repository test — YES.** This is the correct answer. T3 asserts `report.status == PASS` for a text whose only table reference is a CTE name colliding with `billing`'s `bil_` prefix. With `attribute_table_identifier` called without `cte_names` (`tools/validate_architecture_gates.py:2190`), that identifier reaches `ATTR_OWNED`/`billing` and the report is `FAIL`. T3 is red today, and it is *supposed* to be.
- **(ii) Landable as an explicit red/xfail marker — technically possible, and I recommend against it.** A `pytest.mark.xfail(strict=True)` would preserve the "MUST FAIL" semantics mechanically and would auto-break on wiring (forcing the directional record). But it commits a repository assertion that state 3 is unreachable — a claim that becomes stale the moment wiring lands, and that is a *different artifact* from what §6 actually asked for ("run in both directions and the result recorded"). It also puts a non-green marker into a suite whose only current assurance value is that it is uniformly green.
- **(iii) Satisfiable against the pure helper under some defensible reading — NO.** There is no such reading. T3 is specified as a live test driving `run_module_deps_gate` through the `_md_run`/`_md_module` harness; there is no pure-helper restatement of it that preserves what it exists to prove (that state 3 is *reachable from the live path at all*).

**Disposition:** T3 is deferred in full to the wiring increment, where it is that increment's primary acceptance test — executed red immediately before the two-line loop change and green immediately after, with **both captured outputs** in that increment's evidence record. T3 does not block the pure-subset work, and the pure-subset work does not relax T3.

---

### (c) May ADR-011 risk adjudication (D3.2 / D9) legally occur BEFORE live-gate green?

**YES — and it must. Live-gate green is downstream of the adjudication, never a precondition for it.**

Governing clauses, in order of directness:

1. `GATE2-R1-D6-CTE-STATEMENT-SCOPE-LEAD-QUALIFICATION-2026-10-05.md` §2(b) item 5 frames the open question as: "does D3.2 state 3 tolerate being reachable through a lexer-only recognizer whose false-binding exposure is bounded only relative to a rejected design?" — and calls it "an **ADR-011 question, not an implementation one**." A judgment about whether state 3 *may be reachable* cannot be conditioned on evidence that only exists once it *is* reachable; that is circular.
2. The same record's §2(a): the residual "is irreducible under the chosen design, so its acceptability is a D3.2/D9 judgement, not an implementation detail" — and "**The hold is not lifted.**" The hold forbids wiring; wiring is the only route to live green. So the adjudication is necessarily pre-green.
3. `GATE2-R1-D6-ONE-PASS-PURE-SCOPES-VERIFICATION-2026-10-05.md` §"Open gate" records the ordering explicitly: "repository-resident T1–T9/property corpus and then a fresh ADR-011 D3.2/D9 risk judgment **before any `_scan_sql_text` wiring**."
4. `knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md`, Follow-up → "For the independent round-2 reviewer": "Judge whether this ADR itself has a gap — if so, report it as a finding against ADR-011, which `veyro-lead` amends." No clause anywhere in ADR-011 conditions an amendment, or a finding against it, on passing tests.
5. `GATE2-R1-D6-CTE-STATEMENT-SCOPE-CORRECTION-2026-10-05.md` §5, closing: "if a reviewer concludes the trust predicate narrows D3.2 state 3 too far, that is a finding against ADR-011 for `veyro-lead` to amend, not something to widen in implementation."

The prior lead's ordering therefore **survives on this point**. The adjudication's three legal outcomes are: state 3 may be wired as designed; state 3 stays unreachable with the gap disclosed under D8; or ADR-011 is amended. Only the first unlocks the wiring increment.

---

### (d) Is "land T1–T9 then adjudicate" amended?

**AMENDED** (not upheld as-is, not superseded). The instruction's *intent* — repository-resident soundness evidence before the risk judgment — is upheld in full. Its *literal scope* is corrected, because "T1–T9" conflates pure and live tests, and the live ones are either unlandable (T3, T6) or vacuous (T2, T4) in the state-3-unwired state that the one-pass increment deliberately chose and verified.

Corrected ordering:

1. **Pure-subset increment.** Land T1 (including the absent T1c RECURSIVE assertion), **T8**, and **T9** green in-repository against `_cte_scopes`. T5 and T7 appear already covered by the existing 14 tests; a session must confirm that assertion-for-assertion against §6's text rather than at the name level, and add whatever is missing.
2. **Seeded property/fuzz corpus increment.** Correction §6.1's "honest next step," landed in-repository with its seed and token alphabet recorded, so the 300k claim stops being a deleted-prototype assertion. **Stdlib `random` only** — adopting `hypothesis` would be a `CAPABILITY_POLICY.md` lifecycle item by the same reasoning ADR-011 D9 applies to third-party SQL parsers, with BUG-038 as the project's own precedent for skipping it.
3. **Fresh bounded named-`veyro-lead` ADR-011 D3.2/D9 adjudication** on that evidence. This is where the prior lead's "then adjudicate" lands, unchanged.
4. **Only if (3) permits wiring:** the wiring increment (the two-line attribution-loop change in §2.3 plus correction §2.1's verbatim D8 disclosure), carrying **T2, T3, T4, T6** as its own acceptance set, with T3 and T6's control executed and recorded **in both directions**, and M1–M4 plus the §5 M2-outcome-recording amendment run in a throwaway copy.
5. **Round-2 independent code review** — a separate track, and the gate on scenario promotion, not on increments.

T2 and T4 are deliberately moved from step 1 to step 4 despite being green-now: landing them without their T3/T6 controls manufactures exactly the misleading green the round-1 reviewer warned about ("The 90 passing tests are genuinely informative about the paths they cover — they simply do not reach any of the P0/P1 surfaces above, which is why a green suite is not evidence here").

---

### (e) The smallest next legal subgoal

**One pure-test-only increment: add three tests — T1c, T8, T9 — to the existing `GATE2-R1-D6-ONE-PASS-CTE-SCOPES-2026-10-05` section of `/Users/ahmadmabrouk/Desktop/Veyro/tools/tests/test_validate_architecture_gates.py` (currently ending at line ~3455), touching no product source.**

- **T1c** — `WITH RECURSIVE r AS (SELECT 1) SELECT * FROM r; SELECT * FROM r`, assert both scopes' binding sets empty (decision §6 T1, third input).
- **T8** — I-5 extraction equivalence via `Counter` over each scope's `_extract_table_identifiers` versus the whole text, across the T1/T5/T7 inputs plus the unterminated-literal and backslash-escape shapes, plus the "no `fake` binding in any scope" assertion (decision §6 T8).
- **T9** — `N(s) <= _collect_cte_names(T)` over that corpus **plus** correction §3.1's eight adversarial seeds, with the non-vacuity control (correction §5 T9).

Why this is the smallest legal unit: all three are pure assertions on one already-existing, already-verified helper; none requires wiring, a signature change, a new error code, a new dependency, or an ADR amendment; and the increment's cheapest completeness proof is that `tools/validate_architecture_gates.py`'s SHA-256 is **unchanged at `3e05a5108061cd1bf56a27a6e9d1896df3793ec6b9df919664a7cd692d16ed5d`** afterwards — a one-line mechanical check that nothing was wired. The seeded property corpus is the *next* increment, not this one, to keep this one bounded.

**Routing: `veyro-implementer`, Sonnet.** `knowledge/00-System/DEVELOPMENT_CONSTITUTION.md:19` — "**Sonnet:** routine implementation, deterministic test authoring." ADR-011's Conformance determination pins it: "implementation routes to `veyro-implementer` (Sonnet) per the existing mapping, and any rerouting would be an ADR-005 amendment, not a silent change." The `:20` auto-escalation rule does not fire: ADR-011 D8 states this gate is explicitly **not** a security boundary ("The security boundary for tenant and domain isolation is gate 1 (RLS) plus database grants"), the increment touches no data model, no cross-module runtime, and no owner-restricted surface; and ADR-005's blocking scope is "the three named slices" (ADR-005 line 154), which a `tools/` CI-lint test file is not.

**On the open BLOCKED round-1 code review — it is NOT the smallest next subgoal, and it does not block this increment.** My basis, from direct inspection rather than from the review record's summary:

- The P0 is **R1-F01** — "Cross-domain raw SQL is defeatable by identifier form: `public.`-qualification or upper-casing yields a silent PASS" (`knowledge/03-Modules/MOD-001/evidence/code-review/GATE2-MODULE-DEPS-CODE-REVIEW-ROUND1-2026-10-05.md` §4). It is an **adjudicated and implemented** finding, not an open implementation task: ADR-011 D3.1/D3.3 is its adjudication, and `attribute_table_identifier` (`tools/validate_architecture_gates.py:2063-2128`) implements segment casefolding, quoted-segment case preservation, default-schema stripping (D3.3 rule 2), the 3+-part → unattributed rule (D3.3 rule 1), and the schema-owner/prefix-owner conflict rule (D3.3 rule 4). Live and unit regression tests for the `public.`-qualified, upper-cased, quoted, and three-part shapes are present at test-file lines 1482, 1685, 1726, 2572, and 2590.
- What remains open is the **verdict**, and ADR-011's Consequences section is explicit about who can clear it: "the round-1 **BLOCKED** verdict stands until a fresh independent round-2 review says otherwise." I am constrained from opening, dispatching, or claiming that round.
- That review gates **scenario promotion**, not increment authoring. The reviewer's own routing note asks that the P0/P1s "should be adjudicated before SCN-MOD001-006/007/095/096 go to scenario review." Nothing in the review record, ADR-011, or the three D6 records makes an open BLOCKED review a bar on continued bounded implementation increments on the same surface.

So the standing gate ahead of *everything downstream* is the round-2 independent review, and that belongs to the orchestrator's dispatch queue, not to this subgoal. I have **not** verified that the seven P1s, six P2s, and seven P3s are remediated — only the P0's remediation shape — so I cannot and do not assert that the surface is ready for round 2.

---

### (f) Stated limits

**Verified first-hand (direct read or direct execution):**
- `_scan_sql_text`'s attribution loop calls `attribute_table_identifier(ident, modules, importer, default_schema)` with no `cte_names` argument, and contains no `_cte_scopes` call — state 3 is genuinely unreachable from the live path. Read at `tools/validate_architecture_gates.py:2130-2203`, cross-checked by grep across the whole file.
- `_cte_scopes`' full implementation (`:2725-2855`), including the one-pass dispatch, the depth-0 `WITH` → `_parse_cte_binding_list` cursor jump, and the trust predicate applied to the final sliced segment text.
- `_split_sql_statements` does not exist anywhere in the source.
- T1 (all three inputs), T5, T7 (both forms), T8 (I-5 + both unlexable shapes) and T9 (subset + non-vacuity) behaviours, by executing the current helper read-only.
- `_md_base_modules()`'s contents (`tools/tests/test_validate_architecture_gates.py:1220-1222`), which is what makes T6's `scratch_cte` unattributed.
- Both file hashes, byte-identical to the verification record's recorded values.

**Taken from evidence records, NOT independently verified:**
- The **214/214 focused-suite PASS**, the ruff/`py_compile` results, the 4/4 baseline-hash match, and the child-transcript `mr_verify.py` attestations. I executed no pytest run at all.
- The **300k+8 fuzz result** (correction §3.1). The prototype is deleted; the exact seeds are not in the repository. Unreproducible as recorded — which is precisely why step 2 of (d) exists.
- The round-1 review's **P1/P2/P3 findings and their remediation status**. Unaudited by me.
- **TSD §24.1's allow-list wording** and EIP/Blueprint clauses. I did not re-read any governing docx. Correction §6.2 already carries a second-hand-citation caveat forward for §24.1 and decision §7 residual 5; **I inherit that caveat unresolved.**
- **Role/model attestations** in all four D6 records. The correction record's `veyro-lead` attribution remains unverified (`isSidechain=false`, no `agentId`) per qualification §2(b)'s closing note; I have not cured that, and its "live wiring may proceed" disposition is **not** inherited here.

**Reasoned-but-not-executed (a future session must confirm):**
- The T2/T3/T4/T6 dispositions are derived by reading `_scan_sql_text`, `_attribute_bare_identifier` (`:2039-2060`), `attribute_table_identifier`, and the fixture helpers — **not** by running the live `_md_run` harness. The next session should execute T3 directly and confirm it is red *for the stated reason* (a `CROSS_DOMAIN_SQL_IMPORT` on `bil_scratch`), not for an incidental fixture error.
- T5/T7's repository coverage is asserted at the **name** level plus the handful of lines I read, not diffed assertion-for-assertion against §6's specified text.
- My T9 corpus is a **reconstruction** of §3.1's eight adversarial seeds from their prose descriptions. My 0-violation result is over that reconstruction. The authoring session must re-derive the seeds from §3.1 itself and record what it actually observes, not what I observed.

**Not done, and not proven:**
- **Lemma L is still not proven.** I did not prove it and mounted no new falsification search beyond the 11 inputs above. Its segmentation half is vacuous by construction under the one-pass design; the absolute false-clean residual that the qualification's Finding 3 identified is untouched by anything in this adjudication and remains the subject of step 3.
- No file was written, edited, or created. No review round opened, claimed, or dispatched; `REVIEW_IN_FLIGHT.md` untouched. No scenario status changed — **SCN-MOD001-006/-007/-095/-096 remain NOT EXECUTED and unpromoted**, and no PASS is claimed or inferred anywhere above. No git add/commit/push/stash/reset/clean; all WIP preserved. No owner-reserved action.
- **Disclosure:** my read-only `python3 -c` probes may have refreshed a gitignored bytecode cache under `tools/__pycache__`. No tracked or untracked source file changed; `git status --porcelain tools/` is identical to the session-start snapshot and both file hashes match the verification record exactly.

**Caution for the next session — namespace collision.** `knowledge/00-System/CURRENT_STATE.md` contains an unrelated **"T1-T9"** test/mutant set belonging to BUG-050 / GOV01-R02 Slice-7 (financial invariants). It must not be conflated with D6's T1–T9. Grep for `GATE2-R1-D6` rather than for `T1-T9` when reconciling governance records.

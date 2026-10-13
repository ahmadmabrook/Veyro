# GATE2-R1 D6 — CTE Statement-Scope: Named Lead Architecture Qualification

**Date:** 2026-10-05
**Module:** MOD-001 (active, WIP=1)
**Decision slot:** GATE2-R1 D6 (CTE statement-scope recognizer)
**Role invoked:** `veyro-lead` — registered Veyro architecture / critical-engineering-*decision* role (Opus tier), per ADR-005 and `knowledge/00-System/MODEL_ROUTING.md`
**Scope of this record:** architecture qualification ONLY. Not an independent code review, not a security review, not a scenario verdict, not a Module Approval Certificate, not a PASS.
**Recorder:** top-level orchestrator session (transport/recorder only — this session contributed **no** architecture judgment of its own; everything in §2 is the named lead's return, copied faithfully).

---

## 1. Dispatch provenance and role/model observation

| Item | Observed value |
| --- | --- |
| Dispatch mechanism | `Task`/Agent tool, foreground (not backgrounded) |
| `subagent_type` requested | `veyro-lead` (registered named agent, `.claude/agents/`) |
| Model requested | `opus` (explicit `model` override on the dispatch) |
| Did Task return an actual named `veyro-lead` result? | **Yes.** A real sidechain agent executed and returned, with `agentId: a6e127d040b2cd7c8`, 17 tool uses, 123,181 subagent tokens, ~247s duration. The return cites absolute file paths and specific source line ranges it read, consistent with genuine read-only execution against this working tree. |
| Model **as observed** | **UNVERIFIED.** `opus` was requested on the dispatch; the Agent tool result does not surface the executing model identifier back to the caller, so this session cannot independently attest the model string. Recorded as requested-`opus`, **not** verified-`opus`. |
| `ROLE_UNAVAILABLE`? | No — the registered named role was available and returned a verdict. |

Files the named lead reports having read:

- `knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md`
- `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-D6-CTE-STATEMENT-SCOPE-DECISION-2026-10-05.md`
- `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-D6-CTE-STATEMENT-SCOPE-CORRECTION-2026-10-05.md`
- `tools/validate_architecture_gates.py` (lines 1823, 2063-2205, 2206-2704)
- `tools/tests/test_validate_architecture_gates.py` (CTE section from line 2742)

---

## 2. Named lead verdict (copied faithfully)

### VERDICT

**BLOCKED**

### (a) Technical rationale

**Finding 1 — the implementation prerequisite named by the dispatch does not exist.** Neither `_split_sql_statements` nor `_cte_scopes` is present anywhere in the repository (grep across the tree excluding `knowledge/` returns matches only in the two evidence records), and neither `test_segment_bindings_are_a_subset_of_whole_text_bindings` (T9) nor `test_statement_splitter_and_cte_collector_share_one_dispatch` (T10) exists in `tools/tests/test_validate_architecture_gates.py`. The "implemented guard" the adjudication question presupposes is not implemented. T9/T10 and the 300k-input fuzz exist only as a `/tmp` prototype result recorded in prose; they leave no standing, executable artifact against repository code.

**Finding 2 (decisive) — Lemma L's stated mechanism is false against the source.** Correction §3 grounds Lemma L on the premise that `_collect_cte_names` "walks the same text with **the same three-branch dispatch in the same order**" as `_split_sql_statements`. The source contradicts this in both directions:

- `_collect_cte_names` (`tools/validate_architecture_gates.py:2667-2704`) has the three lexical-region branches **plus** `(`/`)` depth bookkeeping **plus a fourth, depth-0 `WITH` branch** that calls `_parse_cte_binding_list` and then jumps the cursor (`i = end`), consuming whole binding lists atomically via `_skip_balanced_parens` (`:2546-2583`).
- The designed splitter (decision §2.1) has no `WITH` branch at all, and adds a **`;`-at-depth-0 cut branch** that `_collect_cte_names` lacks.

The two walks therefore do not share one dispatch, in either direction. Whether the asymmetry can move a cut index is exactly the unproven part — and **T10, as specified, cannot detect it**: it is scoped to "both call `_lex_quoted_segment` and `_skip_quote_or_comment`, in that order, and neither contains a *lexical-region* branch the other lacks," a property that passes while the `WITH`-jump/`;`-cut asymmetry stays entirely unguarded. **M5 is likewise scoped to a lexical-region branch** (adding `#` to the splitter only) and cannot kill a `WITH`-jump mutant. The guard introduced to lock Lemma L locks a strictly weaker subproperty than Lemma L needs. Per the dispatch constraint, a contradiction between the correction's invariants and the source is a BLOCKED condition, and I will not complete the missing proof.

**Finding 3 — the surviving soundness claim rests on a counterfactual comparator.** I-2a bounds permissiveness against the **naive whole-text wiring**, which the decision record itself classifies as the defect (§1.2 reproduction; §5 row 2 "Rejected — this is the defect"). That design was never live. The actual live baseline is `cte_names=frozenset()` at the single call site (`_scan_sql_text`, `:2190`, documented at `:2138-2145`), i.e. state 3 is currently unreachable and maximally fail-closed. Relative to that real baseline the increment **strictly widens** a clean state (correction I-2b, stated not denied), and the only thing bounding that widening against a *false* binding is Lemma L. There is no second, independent control: the trust predicate is admitted (correction §3, direction 2) to "provide no protection whatsoever" in the false-cut direction, because the character that would trip it is consumed as the cut. So the entire false-clean argument under D3.2 reduces to the one proposition that is unproven and whose stated mechanism is wrong.

**Consequence under ADR-011.** D3.2 state 3 is one of five clean states under §24.1's allow-list reading; decision §1.1 correctly notes an over-wide state 3 is "a silent allow-list extension — precisely the R1-F01 failure class ADR-011 D9 forbids in any form." The finite T9/T10 set plus the trust predicate constrain the **cross-statement** half of the risk class (I-1′, sound) and the **relative-to-naive-wiring** half (I-2a, conditional on L). They do not constrain the **absolute false-clean** half — a false binding manufactured inside one real statement by a lexer under-skip — which correction I-1″ and §6.3 expressly decline to rule out. That residual is irreducible under the chosen design, so its acceptability is a D3.2/D9 judgement, not an implementation detail.

The ORCHESTRATOR QUALIFICATION HOLD conditioned wiring on resolving "the report's expressly unproven Lemma L." Lemma L is not resolved; it is worse than unproven — its premise is falsified by the source. **The hold is not lifted.**

### (b) Smallest next legal subgoal

One bounded increment, **still unwired** — `_scan_sql_text`'s attribution loop is not touched:

1. **Collapse the two walks into one pass.** Implement `_cte_scopes` as a single lexical walk that emits depth-0 statement cuts *and* depth-0 `WITH` bindings from the same dispatch, sharing the `WITH` → `_parse_cte_binding_list` jump. This makes Lemma L vacuous by construction — there is no two-function agreement property left to prove, and T10/M5 become unnecessary rather than under-scoped. This option is not in decision §5's rejected list and is strictly smaller than proving L.
2. If (1) is declined and the two-function shape is kept: restate Lemma L against the actual source as a **cut-index agreement** proposition (at every index where the splitter cuts, the collector's whole-text walk is at depth 0 outside every lexical region, *and* that index is not inside a region the collector's `WITH` jump skipped), name both asymmetries explicitly, restate T10 to assert that property, and add an **M6** mutant attacking the `WITH`-jump asymmetry. Do **not** reach for `N(s) = _collect_cte_names(s) ∩ _collect_cte_names(T)` as a shortcut: it makes I-2a true by construction and buys zero soundness, because a false binding appears in both sets.
3. Land T1–T9 plus the property-based/fuzz test the correction's §6.1 already calls "the honest next step" **in the repository**, with seed and corpus recorded, so the 300k result stops being a deleted-prototype claim.
4. Replace the decision's §2.5 disclosure with the correction's §2.1 verbatim text when the coverage note is eventually written (D8).
5. Then a fresh bounded dispatch adjudicates the one remaining question, which is an **ADR-011 question, not an implementation one**: does D3.2 state 3 tolerate being reachable through a lexer-only recognizer whose false-binding exposure is bounded only relative to a rejected design? If the answer is no, that is a finding against ADR-011 for `veyro-lead` to amend, exactly as decision §7 residual 6 anticipates.

Separately unresolved and not cured by this adjudication: the correction record's `veyro-lead` role attribution remains unverified (`isSidechain=false`, no `agentId`); its "live wiring may proceed" disposition stays provisional and is not inherited here.

### (c) Explicit limit of this adjudication

**Fixture-scoped; real-tree domain ownership DEFERRED and `BLOCKED: OWNER_APPROVAL_REQUIRED`** (ADR-011 scope limit). This verdict decides one bounded proof/implementation question in decision slot D6 and nothing else. No code, test, or governance file was edited; no file was written. No independent code review, no security review, no scenario verdict, no PASS claim — `SCN-MOD001-006/-007/-095/-096` remain NOT EXECUTED and unpromoted, and the round-1 BLOCKED verdict stands. No ADR amendment is made. No owner-reserved action: no spend, no real member data, no production deploy, no material product/pricing/business/architecture/scope change. No `mr_verify.py` attestation was run by that session; the orchestrator should attest the transcript if one is wanted for the record.

---

## 3. Recorder notes (non-architectural, provenance only)

- This session acted strictly as transport and recorder. It did **not** form, supplement, soften, or contest any part of §2. No architecture judgment of this session's own appears in this document.
- Consequent to the BLOCKED verdict, **no CTE wiring was performed** and no file other than this report was created or modified by this session.
- The ORCHESTRATOR QUALIFICATION HOLD recorded in `GATE2-R1-D6-CTE-STATEMENT-SCOPE-CORRECTION-2026-10-05.md` therefore **remains in force**.
- Model attestation limit restated for the record: `opus` was requested; the executing model identifier is **not observable** from the Agent tool result and is recorded as **unverified**.

## 4. Orchestrator independent role/model attestation

The foreground Task call in `/tmp/veyro_gate2_d6_named_lead_qualification_raw.txt` specifies `subagent_type: veyro-lead` and `model: opus`. Its matching sidechain transcript is `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/d38c2b76-ddf4-4fcb-b494-93f27236f3d1/subagents/agent-a6e127d040b2cd7c8.jsonl` (`agentId: a6e127d040b2cd7c8`, `isSidechain: true`). Independent `mr_verify.py` on that **child**, not the top-level transcript, returned **PASS, 29/29 turns, model `claude-opus-5`, required tier `opus`**. This resolves §1/§3 recorder-time model-unverified limitation for this named-lead BLOCKED adjudication only. The prior correction report’s claimed named-role attribution remains unverified; the wiring hold stays in force. Source/test hashes remained unchanged.

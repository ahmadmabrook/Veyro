# Gate-2 R1 D6 — ADR-011 D3.2/D9 pre-wire risk judgment (named `veyro-lead`, Opus, 2026-10-05)

**Scope:** MOD-001 / GOV-01-R04 gate 2, fixture-scoped. Decides exactly one bounded question: may the current pure one-pass `_cte_scopes` be wired as ADR-011 D3.2 state 3, measured against the **actual** live baseline (`cte_names=frozenset()` at the single `_scan_sql_text` call site — state 3 unreachable, maximally fail-closed)? Nothing else is decided. Real-tree domain ownership remains DEFERRED and `BLOCKED: OWNER_APPROVAL_REQUIRED`.

## 1. Verdict

**(B) — HOLD state 3 unreachable, and disclose the gap under D8.**

The one-pass collapse is accepted as a genuine improvement: it makes Lemma L vacuous by construction and so cures the decisive Finding 2 of `GATE2-R1-D6-CTE-STATEMENT-SCOPE-LEAD-QUALIFICATION-2026-10-05.md`. It does **not** cure the residual that blocks wiring, and curing Lemma L was never sufficient on its own.

## 2. Absolute-risk rationale

**2.1 What the one-pass design removes, and what it does not.** Collapsing two walks into one lexical cursor removes the *cut-index agreement* class (two dispatches disagreeing on where a statement ends). The class that governs this decision is untouched: a **shared-lexer under-skip** inside a single real statement. If `_skip_quote_or_comment` / `_lex_quoted_segment` skip *less* than PostgreSQL would, text that is really inert (a comment body, a dollar-quoted body, a literal) is exposed to step 5, a `WITH` is falsely recognised at depth 0, and `_parse_cte_binding_list` returns a name that binds nothing. One shared dispatch does not make a lexer correct; it makes it *consistently* wrong. Sharing eliminates disagreement, not under-skip.

**2.2 Every decline is one-directional; the false-clean path is the false *positive*.** The per-segment `;` predicate and the whole-text decline on an unterminated region can only remove the state-3 branch, never add it — that half of the design is sound and I affirm it. Precisely because of that asymmetry, no control in the current design points at the only route to a false clean, which is an *extra* binding. The trust predicate is structurally incapable of catching one: a falsely-bound name is simply present in the accumulator.

**2.3 The comparator is the real baseline, and the increment strictly widens a clean state.** Today state 3 is unreachable, so every CTE-looking identifier falls through the unchanged precedence chain to state 1/2/4/5 or ERRORs at state 6. That baseline's error mode is a **false fail** (a legitimate CTE name ERRORing as unattributed) — loud, safe, D8-disclosable. Wiring converts some of those into clean-and-counted, and at least one unbounded subclass of that conversion is a **false clean**. Under D3.2, state 3 is one of five clean states on the §24.1 allow-list reading; an over-wide state 3 is a silent allow-list extension, which D9 forbids *in any form*. I do not weigh this against the rejected naive whole-text wiring: relative permissiveness versus a design that was never live is not a safety argument.

**2.4 Two decisive unknowns, each of which changes the residual's size.** Neither is resolvable from the supplied packet, and I decline to infer either:

- **(U1) Dialect under-skip classes are unverified.** The docstring asserts regions are consumed "atomically" but names no behaviour for: nested block comments (PostgreSQL nests `/* /* */ */`; a non-nesting skipper terminates early and exposes real SQL), **tagged** dollar-quoting (`$fn$ … $fn$`, and a tag-mismatched inner `$$`), `E'…\'…'` backslash escapes, `U&'…'` / `U&"…"` unicode-escape forms, and doubled quotes inside a double-quoted identifier. Each is an ordinary-SQL route to an exposed `WITH`, not an exotic adversarial input. The 512-case corpus (57 non-empty-binding segments, 190 multi-scope cases) is a non-vacuity floor, not coverage of these classes, and its own record states finite passing tests do not prove absence of an absolute false-clean. I agree, and will not treat 512 passes as permission.
- **(U2) The D3.2 precedence position of state 3 at the live call site is unverified.** If the attribution chain consults states 1 and 2 **before** state 3, a false binding can never suppress `CROSS_DOMAIN_SQL_IMPORT` or re-attribute an owned table, and the residual collapses to "a state-6 ERROR silently becomes clean for an otherwise-unattributed name" — still a widening, but bounded and arguably disclosable. If state 3 is consulted before state 2, a falsely-bound `bil_invoices` masks a **real cross-domain import**: exactly the R1-F01 class, unacceptable at any probability. I am not authorised in this dispatch to read the call site, so the residual's magnitude is presently unknown. Deciding "may wire" while the worst case is masking a state-2 FAIL would be inferring permission from silence.

**2.5 Why not (A).** (A) requires bounding the residual by constraint. The two constraints that would actually bound it — verified fail-closed behaviour on the U1 classes, and a pinned state-1/2-before-state-3 precedence — are not established facts I may condition on; they are work not yet done. A constraint an agent cannot verify at wiring time is not a constraint.

**2.6 Why not (C).** ADR-011 needs no amendment to hold. D3.2 state 3 already prescribes a *lexical* recognizer ("collected lexically at depth 0") and D9 already rejects a third-party SQL parser in this contract, so "lexical, with a residual" is the ADR's own chosen point on the curve, not a deviation. The current baseline is a conservative under-approximation of state 3 whose only divergence is false-fails — honestly recordable as a D8 coverage gap. An amendment becomes necessary only if, after U1/U2 close, someone proposes to *declare* an irreducible lexical false-clean residual contractually acceptable. That is a later question, and the cheaper path to it is not yet exhausted; amending an ADR to admit a residual before attempting to bound it inverts the fail-closed order.

## 3. Evidence limits of this judgment

Formed from the supplied packet only; no source, test, or ADR file was read, edited, or re-verified by this session. I did not re-read §4.3, `_scan_sql_text`, or the shared lexer helpers. I accept the cited `mr_verify.py` attestations and SHA-256 values as reported, without independent re-computation. This is **not** an independent code review, security review, gate-2 round verdict, or scenario verdict: round-1 independent review remains BLOCKED (P0=1/P1=7/P2=6/P3=7) and `SCN-MOD001-006/-007/-095/-096` remain NOT EXECUTED and unpromoted. No owner-reserved action was taken or implied: no spend, no real member data, no production deploy, no material product/pricing/business/architecture/scope change. No file other than this one was written.

## 4. Next legal action (one bounded, still-unwired increment)

`_scan_sql_text`'s attribution loop is **not** touched. In one guarded operation:

1. Add repository-resident, still-unwired tests closing **U1**: for each named class (nested block comment, tagged dollar-quote incl. tag mismatch, `E''` backslash escape, `U&` unicode-escape forms, doubled quote inside a double-quoted identifier), assert `_cte_scopes` either consumes the region atomically **or** declines fail-closed — and in no case emits a binding sourced from inside it. A class that cannot be shown to do one of those two things is a confirmed defect, not an open question.
2. Record, read-only, the **actual** evaluation order of D3.2 states 1/2 versus 3 at the live call site, closing **U2**. No reordering is authorised by this verdict.
3. Author the **D8 coverage-gap disclosure** mandated by this hold: state 3 is unreachable; legitimate depth-0 `WITH` CTE names therefore reach state 6 `MODULE_DEPS_TABLE_UNATTRIBUTED` rather than clean-and-counted; the divergence is false-fail-only and the hold introduces no false clean. Use the correction record's §2.1 verbatim text per residual 4.

**Named agent/model for that next action:** `veyro-implementer` (**Sonnet**), as a named Task agent under a guarded operation with a durable checkpoint and an independent `mr_verify.py` attestation of its sidechain transcript.

Only after U1 and U2 are closed in the repository may a fresh bounded named `veyro-lead` (**Opus**) dispatch re-decide wiring. Until then the ORCHESTRATOR QUALIFICATION HOLD stands.

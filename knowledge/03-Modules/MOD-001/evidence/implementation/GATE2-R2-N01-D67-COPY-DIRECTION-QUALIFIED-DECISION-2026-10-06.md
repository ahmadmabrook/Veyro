# Gate-2 R1-F01 / R2-N01 — D6.7 COPY direction-token qualified decision

**Status:** DECIDED 2026-10-06. Conforming to the governing baseline; **no owner approval required** (§7).
**Decided by:** `veyro-lead` (registered architecture/ADR-decision role, fresh bounded decision-only dispatch). **Not** the gate-2 implementer, **not** the round-1 or round-2 reviewer. No code, security, scenario, or certification approval is given or implied. No review round is opened, advanced, or simulated. No scenario verdict is promoted. No file was edited by that dispatch and no test was executed.
**Session identity (plain facts for the record, as reported by the deciding agent):** agentId `a92ec560a0eac086b`; `CLAUDE_CODE_SESSION_ID=cbc827a8-0b32-4d09-834d-34bde73498b8`, `CLAUDE_CODE_CHILD_SESSION=1`, `CLAUDE_PID=41462`, parent runner `CODEX_SESSION_ID=01a10cd9-b120-7c31-83c9-78aa341ab1c2`, agent harness `AI_AGENT=claude-code_2-1-274_agent`. Transcript: `~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/cbc827a8-0b32-4d09-834d-34bde73498b8/subagents/agent-a92ec560a0eac086b.jsonl`.
**Runtime model identity as reported by the deciding agent's own environment, quoted verbatim:** "You are powered by the model named Opus 5 (1M context). The exact model ID is claude-opus-5[1m]."
**Model attestation by the deciding agent:** **NONE RUN BY THAT SESSION.** No model-assurance tool was run by the deciding agent against its own transcript. The agent-definition tier of `veyro-lead` is **not itself evidence** of runtime model identity, and the quoted environment string is a self-report, not an attestation.

**Orchestrator-side independent runtime attestation (added by the orchestrating session, not by the deciding agent):** `knowledge/05-QA/tools/mr_verify.py` run by the orchestrating session against the deciding agent's actual transcript (path above), arguments `opus veyro-lead` — **verdict PASS, 28 turns, 100% consistent, `models_observed: ["claude-opus-5"]`, matching the required `opus` tier.** This is the only model-identity claim in this record that rests on execution rather than self-report. Governing baselines independently re-verified by the orchestrating session the same session: `verify_baselines.py` **PASS, 4/4**.

**Role separation note:** the orchestrating session persisted this record and ran the attestation above; it did **not** make or alter the decision. The verdicts, scope, controls, and determinations in §1–§9 are the deciding agent's.

**Inputs inspected by the deciding agent:** ADR-011 (D3, D6, D7, D8, D9, and the full 2026-10-06 D6.7 addendum incl. D6.7.1–.7, Alternatives rejected, Addendum conformance determination, Addendum follow-up); `GATE2-R2-N01-D67-COPY-DIRECTION-ROOT-CAUSE-2026-10-06.md` (9-row probe); `GATE2-MODULE-DEPS-CODE-REVIEW-ROUND2-2026-10-06.md` (R2-N01 rows); `GATE2-R1-D6-U1-U2-QUALIFIED-REDECISION-2026-10-05.md` (§0/§1 head and section map only); `tools/validate_architecture_gates.py` lines ~1495–1530, 2680–2760, 3061–3172, 3173–3470, 3920–4000.
**Question decided (exactly one):** whether a context-sensitive exclusion of COPY's top-level directional `FROM` is permitted under D6.7.1, together with the two bounded sub-questions ADR-011 leaves unclassified.

---

## 0. Verdict in one line

**PERMITTED-ONLY-IF-COUPLED.** Excluding COPY's top-level directional `FROM` is a *correction of a mis-identified position*, not the extractor narrowing D6.7.1 disfavours — D6.7.1's over-approximation is defined relative to the **true** table-position set, and `STDIN` is provably not a member of it, decided structurally at a fixed grammar offset with no guessing. But the exclusion is admissible **only** in one atomic increment that also emits the real COPY table target through the existing shared signal-source/`_table_list_positions` seam; standalone it buys only a better error code while leaving D3.2 state 2 masked, which is exactly the "free optimisation" D6.7.1 forbids. `COPY (SELECT 1) TO STDOUT` **is** the D6.3 zero-table class (clean/counted/disclosed); its current I-1 ERROR is **not** evidence of a true table position. **ADR-011 amendment NOT REQUIRED before code dispatch**, but a **D6.8 clause is required before any record claims R1-F01/R2-N01 closed**. **Not owner-reserved.**

---

## 1. Verdict on the one question — **PERMITTED-ONLY-IF-COUPLED**

### 1.1 The tension, stated rather than papered over

D6.7.1 requires the extractor to be an **over**-approximation and says "**Narrowing the extractor is therefore never a free optimisation** and requires its own recorded decision." Today's context-free `_TABLE_KEYWORD_RE` emits `FROM → STDIN` for `COPY mem_roster FROM STDIN`. Removing that element literally shrinks the extracted multiset by one. That is, on its face, a narrowing.

### 1.2 Why it is nevertheless a correction, not a narrowing (D6.7.1)

D6.7.1's object is "an **over**-approximation of the **true table-position set**." Over-approximation means *extracted ⊇ true*. The COPY direction token is not a member of the true set: in the PostgreSQL `COPY` grammar, the token after a table-target COPY's target (and optional column list) is a **direction** keyword, and what follows it is `STDIN`/`STDOUT`/`PROGRAM`/a file path — never a table. Removing a non-member cannot push the extractor **below** the true set, which is the only thing D6.7.1's monotone bias protects.

D6.7.1's operative safety clause is "**Where the lexer must guess, it guesses toward extracting.**" Here the lexer does not guess: the direction offset is computed positively and locally from the COPY target offset. This is the **identical structural shape** already accepted twice inside D6.7's own implementation history:

- `_using_table_position_matches` excludes a `USING` immediately followed by `(` because a JOIN column list "is a column list, never a table position" (and ADR-011's own Follow-up pins `SELECT a FROM mem_x JOIN mem_y USING (id)` as a **PASS** non-vacuity control).
- `_truncate_table_position_matches` excludes `TRUNCATE TABLE …` and the `GRANT TRUNCATE ON …` privilege name, the latter explicitly because otherwise "the position would resolve to the identifier `on` and reach D3.2 state 6 — **ERROR for a table nobody wrote**."

`FROM → STDIN` is *precisely* "ERROR for a table nobody wrote." The only difference from those two precedents is that they were exclusions inside newly-added sources (net-additive), whereas this one removes an element already in the stream — which is exactly why D6.7.1 routes it through a recorded decision rather than leaving it to the implementer.

### 1.3 Why the exclusion is **not weaker** under D6.7.2's invariant

D6.7.2's invariant is ordered `clean < FAIL/ERROR`: "the gate's outcome must be **no weaker** … than the outcome it would produce for T if the extractor had returned nothing."

Structural proof that the exclusion cannot produce a clean outcome: the exclusion applies only to text containing a literal `COPY` token whose target offset is a table-target form. For such text, `COPY` remains in `_BARE_VERB_FORMS`, so `_has_bare_table_verb_form` fires, so `_implies_table_position` is True, so the `if not positions:` branch takes the `implied` arm and ERRORs. Therefore **positions-empty ⇒ ERROR is guaranteed for every text the exclusion touches.** The exclusion is incapable of producing clean where today produces non-clean. It is net-monotone on D6.7.2's stated ordering standalone, and strictly safety-increasing when coupled.

### 1.4 Why standalone is nevertheless NOT authorized

Standalone, the exclusion changes `COPY bil_invoices FROM STDIN` from ERROR `MODULE_DEPS_TABLE_UNATTRIBUTED` to ERROR `MODULE_DEPS_SOURCE_UNINSPECTABLE`. Both are exit 2, so nothing is weakened — but nothing substantive is gained either:

- D3.2 state 2's mandated outcome is a **FAIL `CROSS_DOMAIN_SQL_IMPORT` naming both modules and both domains**. Standalone, that named violation is still absent.
- D7.2 requires violations and uninspectable findings be reported **partitioned, never collapsed**, precisely because "returning only the uninspectable list discards real violations" (R1-F09). Standalone leaves a real violation sitting in the uninspectable bucket.
- A change whose entire yield is a better error code, bought by shrinking the extracted set, is the textbook instance of the "free optimisation" D6.7.1 names.

Coupled with emitting the real COPY table target, the increment yields, for the table-target form, **one false position removed and one true position added** — net cardinality unchanged, net truth strictly increased, and the target position is what lets `COPY bil_invoices FROM STDIN` reach state 2 FAIL and `COPY mem_roster FROM STDIN` reach state 1 clean.

### 1.5 Why the exclusion is required within the coupled increment, not merely tolerated

The alternative — emit the COPY target **and keep** `FROM → STDIN` — is sound (no masking survives, since `bil_invoices` is now emitted) but is rejected, explicitly:

| Alternative | Consequence | Verdict |
|---|---|---|
| Emit COPY target, retain `FROM → STDIN` (pure D6.7.1, zero narrowing) | `COPY mem_roster FROM STDIN` becomes a **permanent ERROR** for a wholly own-module statement, on one of the most common operational SQL forms in existence. That is precisely the pressure generator D6.3 clause 3 names ("would ERROR on the most common operational SQL in existence, which generates exactly the pressure to weaken the gate"). The ERROR detail also names `STDIN` as an unattributed **table**, a false taxonomic claim under D7.1/D6.7.6 — and D6.7.5's own principle is that a false claim is worse than a disclosed limit | **Rejected** |
| Exclusion alone, no target emission | §1.4 | **Rejected**, and forbidden to the implementer |
| Add `COPY` to `_TABLE_KEYWORD_RE` | The one alternative ADR-011's addendum table explicitly rejects ("Widen `_TABLE_KEYWORD_RE` only"); also reads `(` as a target in the query form | **Rejected** |
| Global `FROM` suppression | Destroys ordinary `SELECT … FROM` and the inner `FROM` of the query form; a catastrophic false-clean | **Rejected**, and forbidden to the implementer |
| Defer the whole family to the D9 parser | R2-N01 is P0 and fixture-scoped; the COPY family's denial must be reliable on fixtures now | **Rejected** |

### 1.6 Retention requirements (absolute, independent of everything above)

- **(a)** The inner `FROM` of `COPY (SELECT … FROM <table>) TO STDOUT` remains a real table position. The exclusion offset is computed **only** for a table-target COPY; the query form yields no exclusion offset at all, so its inner `FROM` is untouched.
- **(b)** Ordinary `SELECT … FROM` remains a real table position, unconditionally, in all text.

### 1.7 Verdict

**PERMITTED-ONLY-IF-COUPLED.** The exclusion is authorized **only** as part of one atomic increment that also emits the real COPY table target through the existing shared seam. The coupling is a property of the **increment**, not merely of the end state: the two changes may not land in separate commits or separate dispatches.

---

## 2. D6.3 I-1 classification of `COPY (SELECT 1) TO STDOUT`

**Classification: the D6.3 zero-table statement class — clean, counted under the clean zero-table counter, and disclosed.** The current ERROR `MODULE_DEPS_SOURCE_UNINSPECTABLE` is **incorrect** as a terminal classification.

Grounds, in D6.3's own words: "A triggered statement with **no table position at all** — `SELECT 1`, `SELECT now()`, `ANALYZE`, a bare `VACUUM` — is **clean, counted, and disclosed under its own counter**." `COPY (SELECT 1) TO STDOUT` references no table whatsoever; it is `SELECT 1` wrapped in a transport verb.

**Explicitly, as asked: the current I-1 ERROR is NOT evidence of a true table position.** It is evidence only that the token `COPY` appeared in the text. `_has_bare_table_verb_form`'s COPY branch is a context-free proxy for its own stated premise — "the table name would follow the verb directly with no table-position keyword in between." In the query form a `(` follows the verb directly, so the proxy's premise is **falsified at that offset**. The live `if not positions:` dangling-branch comment makes the same claim the query form falsifies: "The signal proves a table position is present; only its name is unreachable." For `COPY (SELECT 1) TO STDOUT` no name is unreachable, because there is no name.

Consistency with D6.7's monotone bias: this reclassification **does remove ERROR surface**, which D6.7's own conformance determination says no D6.7 clause does. It is therefore **not** authorized by D6.7 — it is authorized by **D6.3 clause 3**, which is unamended by D6.7 and has always placed zero-table statements in the clean class. The reduction is bounded and provably sound: `_implies_table_position` is only consulted when `positions` is already empty, and it is a disjunction, so the reclassification can change an outcome **only** for text that simultaneously (i) contains a `COPY` every occurrence of which is a balanced, well-formed query form, (ii) yields zero positions from any source, (iii) contains none of `FROM JOIN INTO UPDATE TABLE ONLY REFERENCES USING` anywhere, and (iv) triggers no `TRUNCATE` or `GRANT`/`REVOKE … ON` bare form. That class is exactly `COPY (SELECT 1) TO STDOUT`, `COPY (VALUES (1)) TO STDOUT`, `COPY (SELECT now()) TO STDOUT` — all genuinely table-free. The query form's own inner table references are independent signals and are not lost.

Two fail-closed boundaries on the reclassification, both mandatory:
- An **unbalanced or unterminated** `(` at the COPY target offset is **not** the query form: it is undecidable ⇒ ERROR `MODULE_DEPS_SOURCE_UNINSPECTABLE`.
- Where **any** `COPY` occurrence in the text is a table-target form, the bare-verb-form trigger still fires. The context-sensitive branch fires iff **at least one** occurrence is not a well-formed query form.

---

## 3. ADR-011 amendment — **NOT REQUIRED before code dispatch**

### 3.1 Authorizing clauses, named

| Change | Authorizing clause |
|---|---|
| Emitting the real COPY table target | **D6.7.3** — "the bare-verb forms" are named list positions; the source itself records `COPY` as a *pending* D6.7.3 form. This is completion of D6.7.3 as written, not a new permission. |
| Routing it through the shared seam | **D6.7.2** — the per-position accounting seam, plus **D6.7.4**'s "`_implies_table_position` seam … must be preserved" |
| Excluding the direction token | **D6.7.1, second sentence** — "requires its own **recorded decision**." D6.7.1 specifies a recorded decision, not an ADR amendment. **This record is that decision**, made by the registered `veyro-lead` ADR-decision role. |
| Reclassifying `COPY (SELECT 1) TO STDOUT` | **D6.3 clause 3** — its own zero-table clean/counted/disclosed sentence, applied to a form the clause did not enumerate |

No D6.7 clause is contradicted: D6.7's self-description ("every D6.7 clause **adds** ERROR surface and removes none") remains true of D6.7's clauses, because the single ERROR-surface reduction comes from D6.3, not from D6.7. D6.7.4's vocabulary floor is untouched — `FROM` stays in `_TABLE_POSITION_KEYWORDS`, `COPY` stays in `_BARE_VERB_FORMS` and `_TRIGGER_VERBS`.

### 3.2 What this record must contain to discharge D6.7.1 (all present)

1. The exact token excluded and the exact structural rule deciding it (§1.2, §4, §6).
2. The proof the excluded token is not a member of the true table-position set (§1.2).
3. The proof the exclusion cannot produce clean where today produces non-clean (§1.3).
4. The coupling requirement and why standalone is refused (§1.4, §1.5, §1.7).
5. The retention requirements for the inner `FROM` and ordinary `SELECT … FROM` (§1.6).
6. Mutation controls that would catch a widening, with a stated blocker rule (§5).

### 3.3 Separately: amendment REQUIRED before any closure claim

An amendment is **not** a precondition for the implementation dispatch, but it **is** a precondition for any record claiming R1-F01 / R2-N01 closed, because the precedent set here (a structurally-decided exclusion of a non-table token, and D6.3's zero-table class reaching inside a bare-verb form) must not live only in an evidence file. Minimum necessary clause scope: one new clause **D6.8**, four sub-clauses, adding nothing beyond §1–§2 of this record. Proposed text, for `veyro-lead` to persist in a later dispatch (the deciding dispatch did **not** write it into the ADR, and this record does not constitute an amendment):

> **D6.8 — Direction and option tokens are not table positions, and the zero-table class is decided at the target offset.**
>
> **D6.8.1.** A keyword listed in D6.7.4's vocabulary floor may nevertheless occupy a position in which the grammar fixes it as something other than a table introducer. The top-level `FROM`/`TO` of `COPY <table> FROM|TO STDIN|STDOUT|PROGRAM|<path>` is a **direction** token, not a table position. Excluding such a token is a **correction of a mis-identified position**, not the extractor narrowing D6.7.1 disfavours: D6.7.1's over-approximation is defined relative to the *true* table-position set, and a token that is not a member of that set cannot be removed from below it. The exclusion is admissible only when (i) it is decided **structurally and locally** at an offset the lexer computes positively, never by enumerating the tokens that may follow it, and (ii) it is coupled, **in the same increment**, to emitting the table position the mis-identified token had been standing in for. A standalone exclusion that buys only a better error code is not authorized. Where the offset cannot be computed, the token is **retained** as a position, per D6.7.1's extracting direction.
>
> **D6.8.2.** `_TABLE_POSITION_KEYWORDS` and `_BARE_VERB_FORMS` are never narrowed by a D6.8 exclusion. The exclusion lives in a context-sensitive signal source — the seam D6.7.2 established — so D6.7.4's vocabulary floor and the D6.3 backstop's trigger are unchanged.
>
> **D6.8.3.** D6.3's bare-table-verb list names **verbs**, not every occurrence of them. A `COPY` whose target offset opens a **balanced** parenthesised query (`COPY (SELECT 1) TO STDOUT`) carries no table position at all and is therefore D6.3's zero-table class — clean, counted under the clean zero-table counter, and disclosed — for the same reason `SELECT 1` and a bare `ANALYZE` are. The query form's inner table references remain independent signals and are unaffected. A `COPY` whose parenthesised target is unbalanced, absent, or otherwise undecidable is **not** the query form: it is ERROR `MODULE_DEPS_SOURCE_UNINSPECTABLE`. Where any `COPY` occurrence in the text is a table-target form, the bare-verb-form trigger still fires.
>
> **D6.8.4 — Explicit non-expansion.** D6.8 authorizes nothing beyond the above. It does **not** authorize a third-party SQL parser (**D9**'s deferral stands); does **not** touch D3.2 state 3, `cte_names`, the live call site, the `cte_names` default, or any resolution order (the U1/U2 **B HOLD** continues in force and governs that lane, including its exhaustive §4 prohibition list and its four-item re-opening bar); does **not** change D8's field set, wording, or conditions, and does **not** discharge D6.7.5's completeness-sentence correction; does **not** touch real-tree domain ownership (owner-reserved, unchanged); adds **no** skip, exempt, allowlist, or suppression path; and leaves `GRANT`/`REVOKE … ON` pending under D6.7.3.

---

## 4. Exact authorized scope in `tools/validate_architecture_gates.py`

### 4.1 Authorized to change — exhaustive

1. **New `_COPY_KEYWORD_RE` and `_copy_table_position_matches(text) -> Iterator[re.Match[str]]`**, modelled on `_truncate_table_position_matches`. Yields only the `COPY` matches whose target offset is a **table-target** form (the first non-whitespace character at the target offset is not `(`). A `COPY` whose target is absent, unlexable, or has an unbalanced `(` **is yielded** — D6.7.1's safe direction — so the shared walk records exactly one *unresolved* position.
2. **Append `_copy_table_position_matches` to `_TABLE_POSITION_SIGNAL_SOURCES`**, appended **last**, so existing position-order assertions are unchanged (the same discipline the comment above that tuple records for `_TABLE_KEYWORD_RE` being first).
3. **Add `"COPY"` to `_LIST_POSITION_SIGNALS`** — membership change only, so the target goes through the one shared `_table_list_positions`. No second list implementation, no per-keyword continuation copy.
4. **Replace the bare `_TABLE_KEYWORD_RE.finditer` entry at index 0 of `_TABLE_POSITION_SIGNAL_SOURCES` with a context-sensitive wrapper** (e.g. `_table_keyword_position_matches`) that filters out **exactly** those `FROM` matches sitting at a positively-computed top-level COPY direction offset, and yields **every other match unchanged, in the same order, at the same tuple index**. The predicate must be **offset equality** against the computed direction offset — never pattern-matching `STDIN`/`STDOUT`/`PROGRAM`/path tokens.
5. **Context-sensitise the `COPY` branch of `_has_bare_table_verb_form`** so it fires iff at least one `COPY` occurrence is a table-target form (per §2's two boundaries). The `TRUNCATE` branch and the `GRANT`/`REVOKE … ON` branch are unchanged.
6. **Docstrings and the pending-form notes** at the touched seams (approximately lines 2699, 2854, 3128–3131, 3365–3367, 3452–3454) updated to record that `COPY` is no longer pending and that `GRANT`/`REVOKE … ON` still is.
7. **Controls in `tools/tests/test_validate_architecture_gates.py`** per §5.

### 4.2 MUST NOT change — exhaustive

- `_TABLE_KEYWORD_RE`'s **pattern** (no keyword added or removed).
- `_TABLE_POSITION_KEYWORDS` (no member added or removed; `FROM` stays — D6.7.4 floor).
- `_BARE_VERB_FORMS` membership (`COPY` stays) and `_TRIGGER_VERBS` (D6.1).
- `_implies_table_position`'s disjunction shape and its `_TABLE_POSITION_KEYWORD_RE` branch.
- `_table_list_positions`' walk body; `_lex_target_identifier`; `_target_identifier_after_keyword`; `_unresolved_target_reason`; `_skip_list_element_alias`; `_element_start_after_keyword`; `_identifier_after_keyword`; `_LIST_ITEM_CONTINUATION_RE`; `_KEYWORD_WHITESPACE_RE`. **No new per-keyword branch anywhere in the walk.**
- `_truncate_table_position_matches`, `_using_table_position_matches`, `_REFERENCES_KEYWORD_RE` — behaviour unchanged.
- `_positions_for_signal`'s single dispatch (`_LIST_POSITION_SIGNALS` membership stays the only list/single discriminator).
- `_table_position_results`' loop body; `_extract_table_identifiers`' projection-only character.
- `_scan_sql_text`'s D6.7.2 unresolved-position refusal, the `if not positions:` backstop structure, the clean/implied split, the per-position attribution loop, and the `ident is None` fail-closed branch.
- D3 attribution end to end: `attribute_table_identifier`, `_attribute_bare_identifier`, D3.1 normalisation, D3.3 precedence, D3.4 reserved, D3.5 external declarations.
- **D3.2 state 3, `cte_names`, the live call site, the `cte_names` default, and any resolution order** — the U1/U2 **B HOLD** (`knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-D6-U1-U2-QUALIFIED-REDECISION-2026-10-05.md`) remains binding and governs that lane.
- **D8 report surface:** no field added, removed, renamed, re-worded, or re-conditioned; no `--json` schema change; no change to the coverage note. The **only** D8-adjacent effect authorized is the *arithmetic consequence* of an outcome change on existing counters (e.g. a statement moving between `zero_table.implied`, `zero_table.dangling`, `zero_table.clean`, `zero_table.with_tables`, or `ref_counts`). **D6.7.5's completeness-sentence correction is a separate, still-open obligation and is NOT discharged here.**
- The module docstring paragraph at lines ~249–257 — its correction is the separately-recorded DC-12 obligation, not this increment's.
- **No third-party SQL parser** (`sqlglot`, `pglast`, `sqlparse`) — D9's deferral stands. No new dependency of any kind; stdlib only.
- **No skip, exempt, allowlist, path-pattern, per-module, per-file, or suppression path**, and no widening of `external_table_references` — D9, GOV-01-R04.
- **No `contracts/modules/ownership.json` real-tree domain/prefix binding** — owner-reserved.
- **No global `FROM` suppression** anywhere, under any framing.
- `GRANT`/`REVOKE … ON` bare-verb form — **stays pending D6.7.3, out of scope.**
- No governance-state edit: no `STATUS.md`, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `SCENARIOS.md`, `TEST_RESULTS.md`, or `BUG_REGISTRY.md` verdict/promotion change from the implementation dispatch.

---

## 5. Discriminating controls

Every control is asserted on **both surfaces** — a `.py` string literal and a `.sql` file — and pins **four** things: the outcome code, the exit code, the **position cardinality**, and the **extracted identifier list**. Codes alone are insufficient: the live defect produces the right-looking exit code with the wrong identifier.

| ID | Subject | Required outcome |
|---|---|---|
| C-01 | `COPY mem_roster TO STDOUT` | 1 position; idents `["mem_roster"]`; **PASS exit 0**; own=1, other=0 |
| C-02 | `COPY bil_invoices TO STDOUT` | 1 position; idents `["bil_invoices"]`; **FAIL `CROSS_DOMAIN_SQL_IMPORT` exit 1**; other=1; names both modules and both domains |
| C-03 | `COPY mem_roster FROM STDIN` | **exactly 1** position; idents `["mem_roster"]`; **PASS exit 0**; own=1; **no position whose identifier is `STDIN`** |
| C-04 | `COPY bil_invoices FROM STDIN` | **exactly 1** position; idents `["bil_invoices"]`; **FAIL `CROSS_DOMAIN_SQL_IMPORT` exit 1**; other=1; no `STDIN` position |
| C-05 | `COPY (SELECT * FROM mem_roster) TO STDOUT` | 1 position (the inner `FROM`); idents `["mem_roster"]`; **PASS exit 0**; own=1 |
| C-06 | `COPY (SELECT * FROM bil_invoices) TO STDOUT` | 1 position; idents `["bil_invoices"]`; **FAIL `CROSS_DOMAIN_SQL_IMPORT` exit 1**; other=1 |
| C-07 | `COPY (SELECT 1) TO STDOUT` | **0** positions; idents `[]`; **PASS exit 0**; counted in the **clean** zero-table counter; the implied/dangling counters unchanged |
| C-08 | bare `COPY` (dangling) | ≥1 position, all **unresolved**; idents `[]`; **ERROR `MODULE_DEPS_SOURCE_UNINSPECTABLE` exit 2** |
| C-09 | `SELECT * FROM bil_invoices` | 1 position; idents `["bil_invoices"]`; **FAIL `CROSS_DOMAIN_SQL_IMPORT` exit 1** — ordinary `FROM` unchanged |
| C-10 | `SELECT a FROM mem_roster, mem_events` | 2 positions; idents `["mem_roster","mem_events"]`; **PASS exit 0** (D6.7 non-vacuity; must not regress) |
| C-11 | `SELECT a FROM mem_x JOIN mem_y USING (id)` | **PASS exit 0** (existing non-vacuity; must not regress) |
| C-12 | `COPY mem_roster (a, b) FROM STDIN` | 1 position; idents `["mem_roster"]`; **PASS exit 0**; column list contributes no position; the post-column-list `FROM` still excluded |
| C-13 | `COPY bil_invoices (a, b) FROM STDIN` | 1 position; idents `["bil_invoices"]`; **FAIL exit 1** |
| C-14 | `COPY mem_roster FROM '/tmp/x.csv' WITH (FORMAT csv)` | 1 position; idents `["mem_roster"]`; **PASS exit 0**; no position from the path or the `WITH (...)` clause |
| C-15 | `COPY mem_roster TO PROGRAM 'gzip > /tmp/x.gz'` | 1 position; idents `["mem_roster"]`; **PASS exit 0** |
| C-16 | `COPY "BIL_INVOICES" FROM STDIN` | 1 position; idents `["\"BIL_INVOICES\""]` (quotes and case preserved); **ERROR `MODULE_DEPS_TABLE_UNATTRIBUTED` exit 2** (D3.1 — proves the new source reaches the shared lexer, not a private regex) |
| C-17 | `COPY public.bil_invoices FROM STDIN` | idents `["public.bil_invoices"]`; **FAIL `CROSS_DOMAIN_SQL_IMPORT` exit 1** (D3.3 rule 2 carried through the new source) |
| C-18 | `COPY ONLY mem_roster FROM STDIN` | **exactly 1** position; idents `["mem_roster"]`; **PASS exit 0** — `ONLY` consumed by the shared walk, never a position of its own |
| C-19 | `COPY (SELECT 1` (unbalanced query-form target) | **ERROR `MODULE_DEPS_SOURCE_UNINSPECTABLE` exit 2** |
| C-20 | `COPY mem_roster FROM STDIN; COPY (SELECT 1) TO STDOUT` | As two `.sql` statements: first PASS own=1, second clean zero-table. In a **single un-split** segment: the bare-verb-form trigger still fires (at least one table-target COPY present) |

### 5.1 Mutation controls — every mutant MUST die

| ID | Mutation | Must die on |
|---|---|---|
| **M-C1** | **Omitted COPY-target emission** — remove `_copy_table_position_matches` from `_TABLE_POSITION_SIGNAL_SOURCES`, keep the direction exclusion | C-02 / C-04 (FAIL → ERROR) and C-01 / C-03 (PASS → ERROR) |
| **M-C2** | **Context-free COPY target** — add the source without the query-form exclusion, so `(` is read as a target | C-05 / C-06 (cardinality 2, an unresolved `(`-element ⇒ ERROR instead of PASS/FAIL) |
| **M-C3** | **Global `FROM` suppression** — drop `FROM` from the extractor, or suppress all `FROM` matches | C-09 (FAIL → clean), C-05 / C-06 (inner `FROM` lost), C-10 |
| **M-C4** | **Direction-token misclassification, over-exclusion** — exclude every `FROM` in any text containing `COPY`, rather than only the one at the computed offset | C-05 / C-06, plus a mixed segment containing a COPY and an ordinary `SELECT … FROM bil_invoices` |
| **M-C5** | **Direction-token misclassification, under-exclusion** — retain `FROM → STDIN` | C-03 (cardinality 2, idents containing `STDIN`, PASS → ERROR), C-12, C-14 |
| **M-C6** | **Query-form reclassification over-reach** — make `_has_bare_table_verb_form` stop firing for every `COPY` | C-08 (bare COPY → clean), C-19 |
| **M-C7** | **Second list implementation** — give COPY its own continuation walk instead of `_LIST_POSITION_SIGNALS` membership | C-18 (`ONLY` consumption) and C-16 (quoted-identifier lexing) — the controls that pass only if the shared walk and shared lexer are actually reached |
| **M-C8** | **Position-order regression** — insert the new source before `_TABLE_KEYWORD_RE` in the tuple | An existing pinned position-order assertion, which the implementer must name; if none exists, one must be added **before** the mutant is run |

**A surviving mutant is a blocker for the dispatch, not a note.** The implementer may not record the increment as complete with any mutant alive, and may not weaken, delete, or re-scope a control in order to make a mutant die. Each mutant's result must be recorded with the specific control that killed it.

---

## 6. Fail-closed ambiguity handling

Grounded in D6.7.1 ("where the lexer must guess, it guesses toward extracting") and D6.7.3 ("the walk **continues** rather than stopping"; "an element the lexer cannot reduce to an identifier is ERROR, never dropped").

**The governing one-line invariant the implementer must state and test:** *the exclusion applies only where the direction offset is positively computed; everywhere else, every `FROM` remains a position.*

- **COPY target form undecidable** (the token at the target offset is neither `(` nor the start of a well-formed target): the `COPY` match **is yielded** as a signal; the shared walk records one **unresolved** position ⇒ ERROR `MODULE_DEPS_SOURCE_UNINSPECTABLE`. Never silently skipped. (Same discipline `_truncate_table_position_matches` already documents for a `TRUNCATE` with no whitespace after it.)
- **Unbalanced or unterminated `(`** at the target offset: **not** the query form. Undecidable ⇒ yielded ⇒ unresolved position ⇒ ERROR. The bare-verb-form trigger still fires.
- **Multi-table / comma list after COPY** (not legal PostgreSQL, but lexically reachable): handled by the shared `_table_list_positions`. **Every** element is its own position, individually subject to D6.7.2. Never truncated to the first.
- **`PROGRAM`, file paths, `STDIN`, `STDOUT`, or any unanticipated spelling after the direction keyword**: never a table position, and never enumerated. The exclusion is decided by **offset**, so an unanticipated spelling is excluded for the same structural reason with no token list to fall out of date. `COPY … TO PROGRAM …` needs no special case: `TO` is not in `_TABLE_KEYWORD_RE`, so nothing after it is read as a target.
- **Column list `COPY t (a,b) FROM STDIN`**: the target resolves from the target offset; the balanced group after the target is a column list and contributes **no** position; the direction offset is computed **after** skipping that balanced group. If the group is **unbalanced**, the direction offset is undecidable ⇒ **the exclusion does not apply** (the `FROM` is retained as a position, D6.7.1's extracting direction) **and** the target position is still recorded. Outcome: ERROR, never clean.
- **`WITH (...)` option clause**: contributes no position. The offset computation stops at the direction keyword; nothing after it is read as a target. `WITH` remains a trigger verb only and is not in `_TABLE_POSITION_KEYWORDS`.
- **Top-level versus inner boundary unresolvable** (parenthesis depth cannot be established, or more than one candidate direction offset exists): **the exclusion does not apply.** The `FROM` is retained. The resulting over-extracted position reaches D3.2 state 6 and ERRORs — the safe direction, and strictly the pre-increment behaviour.
- **Any exception inside the new source or the offset computation** must propagate to D7.3's outermost funnel (`MODULE_DEPS_GATE_INTERNAL_ERROR`, exit 2). The new source may **not** catch an exception and return an empty iterator — that would reproduce the silent-drop shape D6.7 exists to remove.

---

## 7. Owner-reserved determination — **NOT owner-reserved; no owner approval required**

Applying the same conformance test the D6.7 addendum applied to itself:

- **TSD scope:** no change. The increment moves the implementation further *toward* §24.1's allow-list wording and §6.3's rejection of "direct repository/table coupling" — `COPY bil_invoices FROM STDIN` from a membership module is §6.3's textbook instance and currently does not FAIL.
- **Domain model:** no change. No directory bound to any domain, prefix, or schema; no manifest authored or made authorable. ADR-011's scope limit is inherited verbatim.
- **Product, pricing, or business decision:** none.
- **Module scope:** none. GOV-01-R04 already requires a deliberate-violation fail-closed proof for gate 2; this makes that proof real for the COPY family.
- **Routing (ADR-005 / DC-17):** unchanged. Implementation remains `veyro-implementer` / Sonnet; independent review remains `veyro-code-reviewer` / Opus, fresh context. DC-17's routing-change sub-clause is not triggered.
- **Capability (`CAPABILITY_POLICY.md`):** none. Stdlib-only lexical work — one context-sensitive signal source, one balanced-parenthesis offset computation, one frozenset membership, one filter wrapper. All lexically decidable. The parser-requiring alternative was identified and rejected (§1.5), so **D9's deferral stands** and no registry row is needed.
- **Spend:** none. **Real member data:** none — synthetic `mem_` / `bil_` fixtures only. **Production:** untouched. **Deploy or promotion:** none.
- **Material architecture change:** no. For the table-target COPY form the net effect is one false position removed and one true position added, and the only ERROR-surface reduction is the correct application of an existing D6.3 clause to statements that provably carry no table position at all.

**Verdict, plainly: this is not a material product, pricing, business, architecture, or scope change under `.claude/rules/global/owner-reserved-restrictions.md`. No owner approval is required.**

The one owner-reserved item on this surface — committing `contracts/modules/ownership.json` with real domain and owned-table-prefix bindings for the six `backend/app/modules/` scaffolds — remains **`BLOCKED: OWNER_APPROVAL_REQUIRED`**, is untouched by this decision, and is not a dependency of it.

---

## 8. Next legal implementation boundary

**Next legal action:** ONE bounded implementation dispatch to **`veyro-implementer` (Sonnet, fresh context)** to land §4.1 and §6 and the controls in §5 as a **single atomic increment**. The direction-token exclusion and the COPY-target emission may **not** land in separate commits or separate dispatches — §1.7's coupling is a property of the increment, not of the end state. Required evidence: a record under `knowledge/03-Modules/MOD-001/evidence/implementation/` pinning C-01…C-20 on **both** surfaces with position cardinality and extracted identifier lists, plus all eight mutation results with the control that killed each.

**Then, and only then:** a **round-3 independent code review** by `veyro-code-reviewer` (Opus, fresh context), which must independently re-execute the 9-row probe table from `GATE2-R2-N01-D67-COPY-DIRECTION-ROOT-CAUSE-2026-10-06.md` and C-01…C-20. **This decision is an input to that review, never an approval of it (DC-14).**

**Remaining blocked or unchanged:**

- **U1/U2 B HOLD** — D3.2 state 3, `cte_names`, the live call site, the `cte_names` default, and any resolution order remain held under `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-D6-U1-U2-QUALIFIED-REDECISION-2026-10-05.md`, including its exhaustive §4 prohibition list and its non-negotiable four-item re-opening bar.
- **D9 parser deferral** — no `sqlglot` / `pglast` / `sqlparse`; no skip, exempt, allowlist, or suppression path of any kind.
- **Owner-reserved real-tree ownership binding** — `BLOCKED: OWNER_APPROVAL_REQUIRED`.
- **D6.7.5's D8 completeness-sentence correction** and the **DC-12 module-docstring correction at `tools/validate_architecture_gates.py:249-257`** — separate, still-open obligations. This increment discharges neither, and no remediation record may claim this work finished until both are done.
- **`GRANT` / `REVOKE … ON`** bare-verb form — still pending under D6.7.3, out of scope here.
- **ADR-011 D6.8 amendment** — not required before code dispatch (§3.1), **required before any record claims R1-F01 / R2-N01 closed** (§3.3). `veyro-lead` writes it; the deciding dispatch did not, and this record is not it.
- **Scenario state** — SCN-MOD001-006 / -007 / -095 / -096 remain **NOT EXECUTED** and unpromoted. **Nothing is promoted by this decision.**
- **Round-2 verdict** — **BLOCKED** (P0=1 / P1=1 / P2=2 / P3=2) stands. **R1-F01 / R2-N01 remain formally OPEN.**
- **MOD-001 remains uncertified. WIP=1 holds. MOD-002 stays locked.**

---

## 9. What this record does and does not establish

**It is:** a bounded architecture decision by the registered `veyro-lead` role, discharging D6.7.1's "own recorded decision" requirement for one extractor change, classifying one statement form under D6.3, and fixing the exact scope, controls, and ambiguity handling for one implementation dispatch.

**It is not:** an independent code review, a security review, a gate-2 round verdict, a scenario verdict, a module certification, an implementation, or an ADR amendment. It advances no review counter, promotes no scenario, edits no code or test, and executes no gate test. It grants no approval for anything outside §4.1, and the prohibitions in §4.2 are not negotiable by the implementer.

**Orchestration note:** this file is the only file written for this decision. No code, test, ADR, scenario, status, handoff, registry, or review-claim file was edited. `REVIEW_IN_FLIGHT.md` was `CLEAR` at the start of the orchestrating session and was deliberately left untouched — an architecture-decision dispatch is not one of the four review classes that file's protocol governs (security, scenario-catalog, code, gatekeeper), and no review was dispatched.

---

### Files relevant to this decision (absolute paths)

- `/Users/ahmadmabrouk/Desktop/Veyro/knowledge/04-Decisions/ADR-011-gate2-module-deps-input-contract.md`
- `/Users/ahmadmabrouk/Desktop/Veyro/knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R2-N01-D67-COPY-DIRECTION-ROOT-CAUSE-2026-10-06.md`
- `/Users/ahmadmabrouk/Desktop/Veyro/knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R2-N01-N02-QUALIFIED-ROOT-CAUSE-2026-10-06.md`
- `/Users/ahmadmabrouk/Desktop/Veyro/knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-D6-U1-U2-QUALIFIED-REDECISION-2026-10-05.md`
- `/Users/ahmadmabrouk/Desktop/Veyro/knowledge/03-Modules/MOD-001/evidence/code-review/GATE2-MODULE-DEPS-CODE-REVIEW-ROUND2-2026-10-06.md`
- `/Users/ahmadmabrouk/Desktop/Veyro/tools/validate_architecture_gates.py`
- `/Users/ahmadmabrouk/Desktop/Veyro/tools/tests/test_validate_architecture_gates.py`

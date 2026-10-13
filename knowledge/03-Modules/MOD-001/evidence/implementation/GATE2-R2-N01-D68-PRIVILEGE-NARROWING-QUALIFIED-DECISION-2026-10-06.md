---
doc: GATE2-R2-N01-D68-PRIVILEGE-NARROWING-QUALIFIED-DECISION
module: MOD-001
work_unit: GOV-01-R04 — TSD §24.1 gate 2 (module-dependency / cross-domain SQL lint)
operation: 4abbf2af-da25-4ed5-ab98-c167424ce18e
operation_kind: root_cause
subgoal: R04-GATE2-R2-N01-D68-PRIVILEGE-NARROWING-QUALIFIED-DECISION
scenarios_in_scope: SCN-MOD001-006, SCN-MOD001-007, SCN-MOD001-095, SCN-MOD001-096
date: 2026-10-06
role: veyro-lead (registered architecture / ADR-decision role, Opus tier, fresh
  DECISION-ONLY bounded dispatch). NOT the gate-2 implementer. NOT the round-1 reviewer.
  NOT the round-2 reviewer. NOT an independent code review, NOT a security review, NOT a
  gate-2 round verdict, NOT a scenario verdict, NOT a module certification. Advances no
  review counter.
model: claude-opus-5[1m] — Opus 5 (1M context), as reported by this environment
model_attestation: NONE RUN BY THIS SESSION — see §2
transcript_identity: NOT AVAILABLE — see §2
decision_type: qualified narrowing adjudication / ADR-011 amendment (addendum D6.8)
primary_outcome: D6.8 GRANTED (bounded). The privilege-list narrowing is conforming,
  within veyro-lead's delegated ADR-011 authority, and requires NO owner approval.
  Recorded as a dated addendum appended to ADR-011; all prior ADR-011 text, including the
  D6.7 addendum, preserved byte-unchanged.
b_hold_verdict: B HOLD CONTINUES, unchanged, unreopened, untouched.
scenario_verdict: NO SCENARIO PROMOTED. SCN-MOD001-006/-007/-095/-096 remain NOT EXECUTED
  and unpromoted. MOD-001 uncertified. WIP=1; MOD-002 locked.
start_source_sha256: 8cb5790a0628090d26831780e35114db9be92162b49d7b6205bc1a69ec36d077
end_source_sha256: 8cb5790a0628090d26831780e35114db9be92162b49d7b6205bc1a69ec36d077
start_tests_sha256: c0241fa26011f26a6c6d6b839ab1ad07aa995d1023c95e252a433d930b7c36e1
end_tests_sha256: c0241fa26011f26a6c6d6b839ab1ad07aa995d1023c95e252a433d930b7c36e1
git_head: e481b814a80923849dddfe7a49319112aae7b023 (unchanged by this session)
fixture_scope: fixture-scoped; real-tree domain ownership DEFERRED and separately
  BLOCKED: OWNER_APPROVAL_REQUIRED
---

# Gate-2 R2-N01 / D6.8 — privilege-list narrowing: qualified decision (2026-10-06)

## 1. Verdict

> **DECIDED: D6.8 GRANTED (bounded).**

`GRANT`/`REVOKE` privilege-list tokens that collide with table-position signal keywords —
today exactly `UPDATE`, `REFERENCES` and `TRUNCATE` — **may** be excluded from ADR-011
D6.7's table-position signal stream, under a positively-computed privilege-list region, at
parenthesis depth 0, **at one accounting-visible merge point**, and **only** where that
region is positively computed; where it is not, the signal is **retained**. No true table
position is lost under that rule — argued constructively and verified by probe. The decision
is recorded as **ADR-011 addendum D6.8**, appended; all prior ADR-011 text, including the
2026-10-06 D6.7 addendum, is preserved **byte-unchanged**.

**Half (1) first is satisfied, not assumed.** The ordering constraint the root-cause record
§6.3 declared FORCED is already met: half (1) landed in the live source before this dispatch,
and this session re-verified it directly (§5).

No owner approval is required (§8). No scenario is promoted. R1-F01 is not closed.

## 2. Named role, identity, and what was not run

- **Role:** `veyro-lead`, the registered architecture/ADR-decision role.
- **Model:** `claude-opus-5[1m]` — Opus 5 (1M context), as reported by this environment.
- **Dispatch character:** a fresh, DECISION-ONLY bounded dispatch. This session is **not**
  the gate-2 implementer and **not** either the round-1 or the round-2 reviewer. It has no
  Write or Edit tool, by design: the addendum text was authored here and applied to disk by
  the orchestrating session.
- **Transcript identity:** this environment **does not expose an `agentId` or session
  identifier to this session**. Stated exactly rather than invented. The orchestrator holds
  the transcript identity and should record it alongside this file if one is wanted.
- **Model attestation: NONE RUN BY THIS SESSION.** `mr_verify.py` was not run against this
  dispatch's own transcript. Self-attestation of model identity is of little value — a
  session attesting itself proves nothing an independent check does not — and the tool is the
  orchestrating session's to run against the actual transcript. Stated rather than omitted.

## 3. What this record is / is not

**What it is.** A qualified narrowing adjudication, producing exactly two artifacts: the
ADR-011 D6.8 addendum text, and this decision evidence file. It discharges
`GATE2-R2-N01-D67-REMAINING-SIGNAL-ROOT-CAUSE-2026-10-06.md` §6.1 half (2), whose §6.3
reserved the adjudication to `veyro-lead` and not to itself.

**What it is not.** No implementation. No test edit. No review of any kind. No D8 replay. No
scenario execution or promotion. No module certification. No live CTE state-3 wiring. No
`AUTONOMOUS_CONVERGENCE_STATE.json` edit. No owner approval sought, assumed, or implied. No
new capability, dependency or paid service. No third-party SQL parser.

**Integrity — no source or test edit.**

| | SHA-256 | |
|---|---|---|
| `tools/validate_architecture_gates.py` | `8cb5790a0628090d26831780e35114db9be92162b49d7b6205bc1a69ec36d077` | at session start **and** end — byte-identical |
| `tools/tests/test_validate_architecture_gates.py` | `c0241fa26011f26a6c6d6b839ab1ad07aa995d1023c95e252a433d930b7c36e1` | at session start **and** end — byte-identical |

`git status --porcelain tools/` at both start and end shows the same five entries: three
pre-existing modified migration-ordering/capability-manifest files, and
`tools/validate_architecture_gates.py` plus `tools/tests/test_validate_architecture_gates.py`
still **untracked WIP** with no modification. `HEAD` is `e481b81`, unchanged. The working
tree carries **456** uncommitted entries at both start and end — all pre-existing WIP
preserved; nothing committed, pushed, reset, stashed, or discarded.

**Hash reconciliation, stated because it differs from the predecessor record.** The
root-cause record cites source `50e86cca…` / tests `13f61a4c…`. Those are **superseded**: the
half-(1) bounding repair landed between that record (07:37) and this dispatch, producing
`8cb5790a…` / `c0241fa2…` as recorded in
`GATE2-R2-N01-D67-REVOKE-FROM-BOUNDED-P0-LOCAL-VERIFICATION-2026-10-06.md`. This session
re-hashed both files itself rather than taking either record's figure on trust, and verified
the behavioural consequence directly (§5).

**Probe hygiene.** Every probe ran from throwaway files under `/tmp/veyro-d68-probe/`
(`load.py`, `cand.py`), loading the repository module read-only via `importlib` and
implementing the candidate predicate as **probe-local** functions. The repository source was
never patched, not even in a scratch copy inside the repository. No fixture tree was created
inside the repository. No real member data was used anywhere.

**Baseline integrity.** `verify_baselines.py` **PASS 4/4** this session against
`PROJECT_INDEX.md` (Blueprint `80f4b381…`, TSD `0d41c8a1…`, EIP `e5b5ec3b…`, design bundle
`c96f77ab…`). Precedence applied throughout: Blueprint > TSD v1.4.1 > design bundle > EIP
v1.4.1. TSD §24.1's gate-2 paragraph and §6.3's rule were re-read first-hand from
`knowledge/00-System/TSD_MIRROR.md` and confirm ADR-011's quotation faithful — not taken from
ADR-011's own citation.

## 4. The reasoning and causal chain

D6.7.1 made extraction a deliberate over-approximation, for the mirror of D6.1's reason. The
privilege-word collision is over-extraction in the **safe** direction: `UPDATE` and
`REFERENCES` are PostgreSQL privilege names as well as table-position signal keywords, so
`GRANT UPDATE ON mem_roster TO r` yields a spurious position whose target is the reserved
word `ON`. No composition of that defect alone produces a clean pass — the identifier `on` is
owned by no module.

It nevertheless defeats things ADR-011 requires. Measured (root-cause §4.2, re-derived from
this session's own position-stream probes): rows **2A/2B** refuse a wholly own-domain
legitimate grant naming a table nobody wrote; row **2C** emits the correct
`CROSS_DOMAIN_SQL_IMPORT` but under ERROR status, so SCN-MOD001-007's requirement that the
denial name the right thing is met only partially; row **2D** prints the violation **twice**
and D8 reports **4** references where **2** exist, because the privilege word is also a
`_LIST_POSITION_SIGNALS` member and walks the object comma list a second time. Rows 2A–2D are
D3.2 state-precision and **D6.7.5** count-truthfulness defects.

The decisive constraint is root-cause §5's **measured composite result**: the over-extraction
was an *accidental backstop* over part of half (1)'s false-PASS surface. Narrowing it is
therefore not a free optimisation and had to be sequenced — which is precisely why D6.7.1
requires a recorded decision, and why this record exists rather than a code increment.

## 5. The ordering precondition — verified, not assumed

Half (1) replaced `_revoke_grantee_exclusion_offset`'s unbounded `.search` with a positively
computed, anchored walk. This session verified it directly on the live source:

```
_revoke_grantee_exclusion_offset('REVOKE SELECT ON mem_roster\nSELECT a FROM bil_invoices')
  -> None                                  # was 37 (it stole the unrelated FROM)
_extract_table_identifiers(same text)
  -> ['bil_invoices', 'mem_roster']        # the cross-domain reference is back in the stream
```

Row **1A** is therefore no longer a false PASS, and §6.3's FORCED ordering is **satisfied**.
D6.8 is orderable now and was not orderable before.

The consequence for §5's masking question is measured, not predicted. Under the candidate
rule, row **3A** `REVOKE UPDATE ON mem_roster`⏎`SELECT a FROM bil_invoices` yields positions
`FROM -> bil_invoices` and `ON -> mem_roster` — i.e. it moves from **ERROR exit 2 naming the
fake table `ON`** to **FAIL exit 1 naming `bil_invoices`**. Removing the accidental backstop
**widens nothing**, because the real backstop is now in place. Had half (1) not landed, this
same change would have widened the demonstrated false-PASS surface; the addendum therefore
keeps the ordering as a normative clause with two mechanically checkable observations, so a
future session cannot reach this state by a different route and skip the check.

## 6. The rule as decided

Stated normatively in ADR-011 addendum **D6.8.1–D6.8.6**. In summary:

- **Suppressible set — derived, not hand-listed:** the intersection of a closed PostgreSQL
  privilege-name vocabulary with the union of all `_TABLE_POSITION_SIGNAL_SOURCES` keyword
  tokens. Computed this session as exactly `{UPDATE, REFERENCES, TRUNCATE}`. **`ON` is not in
  it** — `ON` is not a privilege name — which is the second, independent reason the object
  `ON` can never be suppressed.
- **Region:** `R = [verb.end(), on.start())` — lower end **closed**, upper end **OPEN**, so
  the object `ON` lies strictly outside `R` by construction.
- **Positively computed iff:** the existing `_GRANT_PRIVILEGE_GAP_RE` character-class
  fullmatch holds; parentheses are balanced within `R` and depth is 0 at `on.start()`; every
  identifier-shaped token **at depth 0** casefolds into the closed privilege vocabulary; and
  no `"` or other non-identifier, non-separator token appears at depth 0. Content at depth
  ≥ 1 is a column list by grammar and is exempt.
- **Predicate:** suppress `kw` iff its token is in the derived set **and** it lies wholly
  within a positively-computed region (`a <= kw.start()` and `kw.end() <= b`) **and**
  `kw.start()` is at depth 0. Nothing else; no token-content check on what follows.
- **Uncertainty ⇒ RETAIN.** Any failure to compute the bound yields no suppression, and the
  D6.7.2 accounting sees the retention. Absence of a bound never implies suppression.
- **One site:** the predicate is consulted inside `_table_position_results`' source loop,
  between obtaining `kw` and calling `_positions_for_signal` — **not** inside any individual
  signal source. Because D6.8 removes positions, the suppression count must additionally be
  disclosed under D8 on every run including PASS.

## 7. The losslessness argument, and exactly how it was verified

**Constructive core.** Inside a positively-computed region at depth 0, every
identifier-shaped token is a privilege name. Therefore the element offset immediately
following a suppressed signal can hold only another privilege word, a `,`, a `(`, or the
region's terminating object `ON` — **never a table name**, because a table name at depth 0
would have rejected the region. A table-shaped name can appear only at depth ≥ 1 (where
suppression is forbidden) or outside the region (where no suppression applies).

**Probes run, and where.** All in `/tmp/veyro-d68-probe/` (`load.py` loads the repo module
read-only; `cand.py` holds the probe-local candidate), under
`backend/.venv/bin/python`:

1. **Baseline position streams** for rows 2A/2B/2D/2E/2F/2G/2H/2I, the column-list and
   `GRANT TRUNCATE, SELECT` shapes, and rows 1A/3A — reproducing root-cause §4.1's four
   spurious signals and §4.2's double-count independently.
2. **Over-span hazard probe.** `_grant_revoke_object_on_match` was measured to compute an
   `ON` **spanning an entire unrelated statement** when a subject has no depth-0 semicolon.
   This is a genuinely new finding of this session: an interval-only region rule would
   suppress that statement's real `UPDATE -> bil_invoices` position and reach **PASS exit 0**
   — a new false clean of the R2-N01 class. It is the reason D6.8.2's closed-vocabulary check
   exists and is recorded as **load-bearing**, with the interval arithmetic secondary.
3. **Candidate predicate over the measured corpus plus hazards** (20 rows): every intended
   suppression taken, every hazard region **rejected**, every ordinary `UPDATE`/`REFERENCES`
   position retained, both ADR standing controls unchanged, `GRANT SELECT, UPDATE ON
   bil_invoices TO r` still naming `bil_invoices` (D6.8 cannot launder a cross-domain grant),
   and `GRANT UPDATE ON "ON" TO r` still yielding `ON -> "ON"`.
4. **Edge-case probe** (22 rows): case-insensitivity, dangling and verb-only forms,
   `ONLY`/`TABLE` modifiers, `ALL TABLES IN SCHEMA`, `REVOKE GRANT OPTION FOR`, nested and
   unbalanced parentheses, multi-statement subjects, a table quoted `"update"`, and
   `USING`/`INTO`/`TRUNCATE` families. Every delta is an intended suppression; every
   non-GRANT family is untouched.
5. **Depth-1 column-list probe** (9 rows): confirmed the lexer never reads into `(`, so a
   table-shaped name in a column list was never a position; and confirmed
   `GRANT SELECT (UPDATE bil_invoices) ON mem_t TO r` retains the real `bil_invoices`,
   which is what makes D6.8.3's depth-0 condition load-bearing rather than cosmetic.
6. **Differential sweep over 425 SQL-shaped string literals** extracted by `ast` from **both**
   the live `tools/validate_architecture_gates.py` and the live
   `tools/tests/test_validate_architecture_gates.py`. Result: **exactly 4 deltas**, all
   intended — `GRANT UPDATE ON mem_roster TO r`, `GRANT REFERENCES ON mem_roster TO r`,
   `GRANT TRUNCATE, SELECT ON mem_roster TO r`, and one occurrence inside
   `_truncate_table_position_matches`'s own **docstring** (prose, and excluded from SQL
   scanning by D6.4 in any case). **No real table identifier lost in any of the 425.**
7. **Generative adversarial sweep: 3,456 texts** (11 GRANT/REVOKE prefixes × 12 statement
   bodies × 6 suffixes × 4 joiners, including newline and `;` joiners). Two invariants
   asserted mechanically: (a) every resolved identifier other than the unquoted reserved word
   `ON` present under the current extractor is still present under the candidate — **0
   violations**; (b) no text has its position stream emptied by suppression without
   `_implies_table_position` being `True`, i.e. the D6.3 I-1 backstop always still governs —
   **0 violations**.
8. **I-1 backstop confirmation.** `_implies_table_position` and `_has_bare_table_verb_form`
   were measured `True` for every `GRANT`/`REVOKE` carrying an `ON`, including
   `GRANT UPDATE ON ALL TABLES IN SCHEMA mem_private TO r` — the one row where suppression
   empties the stream. It stays **ERROR exit 2**, with the refusal moving from state 6 to the
   I-1 backstop.
9. **Pinned-corpus compatibility.** All thirteen `_D67_*` pinned SQL constants and the
   adjacent assertions at `test_…:3662`, `:3851`, `:3949`, `:3963-3986` were checked. Exactly
   two rows change, and the only assertion over them — `"mem_roster" in
   _extract_table_identifiers(sql)` at `:3963-3977`, which the test file **explicitly** says
   a later increment "must be free to turn these statements clean without rewriting" — is
   satisfied by the candidate. §6.5's compatibility claim is confirmed independently, not
   taken on trust.
10. **Mutant killability.** Eight candidate mutations were implemented probe-locally and run
    against a 20-row corpus. Six are killable and are specified as **M-E8…M-E14** with their
    killing rows. **Three were measured to be equivalent mutants** under the layered defences
    (upper end extended to end of text; upper comparison changed to `kw.start() <= b`;
    suppressible set widened to all `_LIST_POSITION_SIGNALS`) and are therefore specified as
    **pinned-identity assertions instead of mutation kills**. Recorded deliberately: telling
    an independent reviewer to kill an unkillable mutant would be a defect in this decision.

**The limit on all of this, stated plainly.** These are **pure-function** measurements of the
position stream, plus the D3.2/D6.3/D7 mapping. **They are not gate-level runs.** No gate CLI
invocation, no fixture tree, and no D8 replay was performed by this session — the dispatch was
decision-only. The expected exit codes in the addendum's corpus are therefore **derived**, and
the addendum states in terms that the implementer must **measure** each row and that a row
whose measured outcome differs is a **stop-and-report, never a table edit**.

## 8. Alternatives considered and why rejected

Recorded in the addendum's own table (nine alternatives, in the D6.7-addendum form). In brief:
**do nothing** pays a real precision and truthfulness cost for a backstop that half (1) has
made redundant (measured via 1A/3A); **per-source context sensitivity** duplicates the
predicate and adds a sixth filter in root-cause §3.5's blind spot — with the TRUNCATE source
as both precedent and warning, since it reaches `GRANT TRUNCATE ON t` but not
`GRANT TRUNCATE, SELECT ON t`; **removing the keywords from the vocabulary** is measured
unsound, converting rows 2F/2G from FAIL into false cleans; **special-casing the literal `ON`
at attribution time** is content-based, cannot tell the spurious position from a table quoted
`"ON"`, and installs a token allowlist at the attribution layer; **the D9 parser** stays
deferred; **narrowing D6.1's trigger** stays forbidden; and an **interval-only bound without
the vocabulary check** was measured to create a new false clean.

## 9. Acceptance criteria, ordering, and scope boundaries

All normative, in addendum **D6.8.7** (ordering, with two mechanically checkable
observations), **D6.8.9** (9 positive rows, 14 negative rows with exact outcome codes, the two
§5 interaction rows, all on **both** the `.py` and `.sql` surfaces; mutants **M-E8…M-E14**
with their killing rows; two pinned-identity assertions), and **D6.8.10** (explicit
non-expansion). Routing is unchanged: implementation remains `veyro-implementer` (Sonnet) per
ADR-005; **no ADR-005 amendment and no DC-17 routing-change trigger** — judged, not assumed,
on the grounds that every D6.8 obligation is a concrete bounded rule with a stated expected
outcome and a closed corpus.

**Conformance and owner approval — reasoned, not asserted.** D6.8 changes no TSD scope, no
domain model, no product/pricing/business decision, no module scope, no routing and no
capability; it incurs no spend, uses no real member data, touches no production, and asserts
no material architecture change. The amending authority is ADR-011's own Follow-up delegation
plus D6.7.1's explicit "requires its own recorded decision", under the same Verdict B split
that let ADR-011 itself be decided without owner approval. D6.8 is strictly narrower than both
ADR-011 and the D6.7 addendum. **No owner approval is required.**

**The one argument not available, stated honestly.** Unlike D6.1 and D6.7, D6.8 **removes**
ERROR surface, so "impossible to weaken the gate" is **not** available and is **not** claimed.
The safety argument is the conjunction of (i) bounded losslessness, (ii) retention on
uncertainty with the I-1 backstop still governing, (iii) the ordering constraint, and (iv) the
two-surface control corpus with verified-killable mutants. Remove any one and the clause is
not safe.

The one owner-reserved item on this surface — binding the six `backend/app/modules/` scaffolds
to domain codes and owned table prefixes — remains **`BLOCKED: OWNER_APPROVAL_REQUIRED`**, was
untouched, and is **not** a dependency of anything here.

## 10. One open DC-12 precondition, observed not adjudicated

`tools/validate_architecture_gates.py:262-264` **still** reads *"An identifier no module owns
is not flagged — only counted and disclosed in a note, since flagging it would false-FAIL on
CTEs, aliases and catalog tables."* That is the exact "unowned ⇒ benign note" terminal state
**D9** forbids *"in any form"*, documented as current behaviour. The D6.7 Addendum follow-up
already made its correction a precondition for any D6.7 remediation record claiming
completion; this session **confirmed it is still present** and restates it in D6.8's
follow-up. Severity and routing stay as round 2 set them (R2-N04, P2) — this is an observation
of record honesty, not a new finding and not a re-adjudication.

## 11. Governing state retained verbatim, and NOT advanced by this record

- **R1-F01** formal ledger **OPEN**. Its blocker list is **not** reduced by this record.
- Round-2 **BLOCKED, P0=1 / P1=1 / P2=2 / P3=2** — the verdict **stands** and is **not**
  lifted.
- **U1/U2 B HOLD in force**, unchanged and unreopened, including its exhaustive §4 prohibition
  list and its non-negotiable four-item re-opening bar. Live CTE state-3 wiring untouched and
  still forbidden; `cte_names`, its default, the live call site and every resolution order
  untouched.
- The **D8 table-reference figure remains a disclosed lower bound** per D6.7.5, which D6.8
  does not weaken.
- **SCN-MOD001-006 / -007 / -095 / -096: NOT EXECUTED and unpromoted. No scenario PASS.**
- **MOD-001 uncertified. WIP=1. MOD-002 locked.**
- `AUTONOMOUS_CONVERGENCE_STATE.json` untouched. `CURRENT_STATE.md`,
  `CURRENT_HANDOFF.md`, `REVIEW_IN_FLIGHT.md`, the scenario catalog and the evidence index
  were deliberately **not** edited by this session; the orchestrator should reference D6.8 in
  them when next reconciling.
- D3.3/D3.4's silence on state 3's position in the precedence order **remains logged, not
  decided**.

## 12. State after this record

ADR-011 now carries addendum **D6.8** (appended by the orchestrating session; all prior text
including the D6.7 addendum byte-unchanged). No code, test, scenario, review or governance
state moved.

**The next legal operation** is the bounded `veyro-implementer` (Sonnet) dispatch of D6.8.1–
D6.8.6 under D6.8.7's ordering check and D6.8.9's corpus and mutation obligations, together
with the DC-12 documentation corrections D6.8's follow-up enumerates. That dispatch's own
completion is **not** closure: closure of R1-F01 and any lifting of the round-2 BLOCKED
verdict require the fresh-context independent round-3 `veyro-code-reviewer` (Opus) review
ADR-011's follow-up specifies, against the criteria in
`GATE2-R2-N01-D67-REMAINING-SIGNAL-ROOT-CAUSE-2026-10-06.md` §7. **This record and the D6.8
addendum are inputs to that review, never an approval of it (DC-14).** Nothing in this record
authorises either dispatch.

**Orchestrator-side runtime attestation after recovery:** `mr_verify.py` on the actual named-lead transcript `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/b0584623-4066-43d1-85fb-e18fbe73713c/subagents/agent-a0e76a38e6f2791b4.jsonl` returned **PASS, 86 turns, 100% consistent, model `claude-opus-5`, required tier `opus`**. The original outer ACPX operation stopped at its soft no-progress limit after the named lead completed but before writing files; the orchestrator recovered and persisted these exact deliverables from `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/b0584623-4066-43d1-85fb-e18fbe73713c/tool-results/toolu_01MLmx9WcMTrs6tin5SjfnyF.json`. This addendum does not convert the budget stop into an implementation or review verdict.

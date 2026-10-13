---
doc: SLICE-7-gov01-r02-domain-suite-scaffolds-financial-invariant
module: MOD-001
requirement: GOV-01-R02 (routine only — six named domain-suite scaffolds + financial-invariant test harness; NOT the tenant-isolation/RLS or auth-negative-credential critical-slice logic, which ADR-005 Decision 1 reserves to veyro-critical-engineer and which this slice only reuses, never modifies)
scenarios: SCN-MOD001-132, SCN-MOD001-133
date: 2026-10-03
implemented_by: ACPX Claude Code lead session, independently attested 228/228 turns on claude-sonnet-5 (round-3 orchestrator re-verification; exact transcript below)
independent_review: round 1 — knowledge/03-Modules/MOD-001/evidence/code-review/CR-MOD001-GOV01-R02-DOMAIN-SCAFFOLDS-2026-10-03.md (veyro-code-reviewer, Opus, 35/35 turns), BLOCKED P0=0/P1=1/P2=6; round 2 — knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT-SECURITY-REVIEW-2026-10-03.md (veyro-security-reviewer, Opus, 97/97 turns), BLOCKED P0=0/P1=1/P2=3/P3=3; round 3 — knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT-SECURITY-REVIEW-ROUND3-2026-10-03.md (veyro-security-reviewer, Opus, 92/92 turns, distinct agentId), BLOCKED P0=0/P1=0/P2=1/P3=2. All three rounds' findings fixed same implementation session; round 3's fix NOT yet re-reviewed. **Corrected 2026-10-03, round 9 (NR9-1): this field enumerated only rounds 1-3 and was five rounds stale — rounds 4-8 had each already run by the time round 9 found this. Rounds 4-9, summarized (full detail in `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-050-financial-invariant-placeholder-false-clean.md`, the authoritative per-round record — not re-narrated here to avoid a second copy drifting out of sync): round 4 BLOCKED P2=1/P3=2 (NR4-1/NR4-2/NR4-3); round 5 BLOCKED P2=1/P3=1 (NR5-1/NR5-2); round 6 BLOCKED P2=1/P3=2 (NR6-1/NR6-2/NR6-3); round 7 BLOCKED P2=2/P3=1 (NR7-1/NR7-2/NR7-3); round 8 BLOCKED P2=1/P3=0 (NR8-1); round 9 BLOCKED P2=2/P3=2 (NR9-1/NR9-2/NR9-3/NR9-4, this round, review at `.../GOV01-R02-SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT-SECURITY-REVIEW-ROUND9-2026-10-03.md`). Every round from 4 onward found the function's behaviour free of false cleans; every finding has been record-accuracy, not product-defect. Not yet independently re-reviewed past round 9.**
status: IMPLEMENTED, fixed-after-review (three rounds), NOT PROMOTED. SCN-MOD001-132/133 remain unpromoted — both require `veyro-security-reviewer`/Opus per their own routing, and round 3 is that gate's third pass, still BLOCKED (now P2=1/P3=2, down from P1=1 originally). No commit/push. MOD-001 remains IMPLEMENTATION IN PROGRESS; MOD-002 remains locked; WIP=1 respected throughout. **Corrected 2026-10-03, round 9 (NR9-1): "three rounds" and "now P2=1/P3=2" are five rounds stale — this is current as of round 3 only. As of round 9 (this round's own remediation), the slice has been reviewed nine times, remains NOT PROMOTED, and round 9's own verdict was BLOCKED P0=0/P1=0/P2=2/P3=2, all four findings record-accuracy gaps (see `BUG-050…md`'s round-9 section for the live figure — this line is not updated per-round and should not be read as current without checking there). SCN-MOD001-132/133 remain unpromoted; no commit/push; MOD-001 remains IMPLEMENTATION IN PROGRESS, MOD-002 locked, WIP=1 respected — those parts of the original line are still true.**
---

# Slice 7 — GOV-01-R02 routine: six domain-suite scaffolds + financial-invariant test harness

## Scope

Per `REQUIREMENTS.md` GOV-01-R02 and `IMPLEMENTATION.md`'s topology (the
six named `backend/app/modules/{membership,booking,payment,ledger,pos,
access}/` scaffolds plus `backend/tests/contract/
test_financial_invariant_scaffold.py`), this slice implements exactly what
`SCENARIOS.md` SCN-MOD001-132 and SCN-MOD001-133 ask for and nothing else:
documented, empty-but-wired suite scaffolds proving the harness (test
discovery, fixture DB connection, the shared tenant-context resolver) is
live, and a placeholder double-entry-invariant fixture proving the
financial-invariant test harness is live. No real business-domain logic.
The tenant-isolation/RLS harness and the auth negative-credential pattern
(Slice 5, ADR-005 Decision 1) were only reused (`disposable_postgres()`),
never modified or duplicated. R04 (RLS-lint/permission-lint gates) and
SCN-067 were not touched — confirmed by running
`tools/validate_architecture_gates.py --gate module-deps` before and
after this slice, both times correctly reporting `GATE_NOT_IMPLEMENTED`,
never a false PASS.

## Files added

- `backend/app/modules/_shared/tenant_context.py` — `TenantContext`
  dataclass + `TenantContextResolver` Protocol. Explicitly not real
  authentication (TSD ADR-009 / `TEN-002` framing in its own docstring).
- `backend/app/modules/conftest.py` — session-scoped `disposable_postgres()`
  fixture shared by all six domain scaffolds (one container, not six).
- `backend/app/modules/{membership,booking,payment,ledger,pos,access}/
  __init__.py` + `tests/__init__.py` + `tests/test_scaffold_live.py` — one
  placeholder test per domain: DB connectivity + the shared resolver
  contract, nothing else.
- `backend/tests/harness/tenant_context.py` — the test-only
  `StaticTenantContextResolver`, moved here after review (see below).
- `backend/tests/contract/test_domain_scaffold_inventory.py` — a
  test-level (not architecture-gate) check: asserts all six domain
  scaffold files exist, then runs them together via a pytest subprocess +
  junit XML, asserting the full set passed and naming any individual
  failing/missing/skipped domain. SCN-132's own text (Scenario Review
  round 11 correction) explicitly rejected a `--gate module-deps`
  architecture-gate implementation of this check, since that gate is
  cross-domain import/SQL detection only — this stays a test, not a gate.
- `backend/tests/contract/test_financial_invariant_scaffold.py` —
  synthetic double-entry ledger legs; balanced set passes, a lone
  unmatched debit leg fails citing `DEBITS_NE_CREDITS`.

## Independent review: BLOCKED (P1=1), then fixed

A fresh-context `veyro-code-reviewer` (Opus tier per its own agent
definition) reviewed this slice with no memory of how it was built. Full
record: `knowledge/03-Modules/MOD-001/evidence/code-review/
CR-MOD001-GOV01-R02-DOMAIN-SCAFFOLDS-2026-10-03.md`. Verdict on the
original submission: **BLOCKED, P0=0/P1=1/P2=6**.

**P1 (real defect, fixed):** `test_financial_invariant_scaffold.py`
originally compared the *signed sum* of entries to zero instead of
summing debit-side and credit-side amounts separately. The reviewer ran
three probes proving this was wrong: a single genuinely-balanced posting
was wrongly **rejected** (its two signed legs didn't happen to be
represented with opposite signs the way the code expected); two
debit-only legs with no credit side were wrongly **accepted** (because
+10 and -10 summed to zero); and the committed "balanced" fixture and the
negative fixture both only worked by sign-cancellation, not by an actual
debit=credit check. Fixed by introducing an explicit `Side` enum
(DEBIT/CREDIT), requiring strictly positive amounts
(`__post_init__` validation), and comparing `sum(debit amounts)` to
`sum(credit amounts)` directly. Independently re-probed this session
against the reviewer's exact two counter-examples after the fix — both
now behave correctly (see command log below).

**P2s, fixed:**
1. `StaticTenantContextResolver` (a test-only fixture class) was sitting
   in the production `app/modules/_shared/` package. Moved to
   `backend/tests/harness/tenant_context.py`; `_shared/tenant_context.py`
   now holds only the domain-free `TenantContext`/`TenantContextResolver`
   contract, consistent with `architecture.md` control 3.
2. The six domain tests imported the `Conn` type alias from the
   critical-slice `tests.harness.tenant_isolation` module purely for
   typing, an avoidable coupling to code this slice doesn't own. Switched
   to the `Conn` alias already defined in this slice's own
   `app/modules/conftest.py`.
3. `ruff format --check` was not clean on the two new `tests/contract/`
   files (no gate currently enforces this). Ran `ruff format`.

**P2s, not fixed, recorded as honest follow-ups (not this slice's to
fix):**
4. When a domain's scaffold file is *deleted* (not just broken), the
   second inventory test (`test_all_six_domain_scaffolds_pass`) reports
   all six domains as `NOT_COLLECTED` rather than only the missing one —
   because the pytest subprocess fails at collection before running
   anything. This is intentional conservative fail-closed behavior (it
   never claims five domains are clean when collection itself broke), and
   the dedicated `test_all_six_domain_scaffold_paths_exist` check already
   names the specific missing domain on its own. Not changed.
5. These scaffolds depend on `backend/tests/harness/postgres.py`'s
   Colima pin and `authn.py`'s schema provisioning, both of which are
   themselves still uncommitted working-tree changes from Slice 5 (shown
   as `M`, not committed, in `git status`). This slice's new files cannot
   be committed before or independently of that prior uncommitted work —
   they depend on it. Recorded here, not resolved by this slice (commit
   sequencing is for whoever is authorized to commit, not decided here).
6. `CAPABILITY_REGISTRY.md`'s CAP-008 entry currently describes its
   approved use as the tenant-isolation/authn harness specifically; this
   slice adds a second consumer of the same approved Colima/Postgres
   binding. Judged in-scope (same capability, same binding, no new
   engine/image/credential path), but the registry wording could be
   widened for accuracy. Not edited by this slice — a capability-registry
   wording change is outside a routine implementation slice's own scope.

**Independent negative-case repeat:** the reviewer re-ran the SCN-132
fail-closed drill itself, independently, in its own throwaway `/tmp`
copy (not trusting this session's prior drill): broke a domain's
assertion, deleted a domain's file, renamed a domain's test so nothing
collected, and skipped a domain's test. All four cases failed non-zero
and named the correct domain (or reported `NOT_COLLECTED`, per the
intentional-conservative point above) — never silently green. Full
detail in the review's own evidence file.

## This session's own test/lint/type evidence (real execution)

All commands run from `backend/`, using the project's own pinned venv
(`.venv/bin/...`), after the post-review fixes above:

```
.venv/bin/ruff check .                     -> All checks passed!
.venv/bin/ruff format <new files>          -> 1 file reformatted, 24 unchanged
.venv/bin/mypy app tests                   -> Success: no issues found in 47 source files
.venv/bin/pytest -q                        -> 174 passed in 21.67s   (full backend suite, real Colima/Postgres)
```

Direct run of all six domain scaffolds (not through the inventory
wrapper):

```
.venv/bin/pytest -v app/modules/{membership,booking,payment,ledger,pos,access}/tests/test_scaffold_live.py
-> 6 passed in 1.41s
```

Reviewer's P1 counter-examples, re-probed after the fix, both now correct:

```
single correct posting (debit cash 100 / credit revenue 100) -> PASSES (previously wrongly rejected)
two debit-only legs, 10 + 10, no credit side                 -> raises DEBITS_NE_CREDITS: total debits 20 != total credits 0
                                                                  (previously wrongly accepted via sign-cancellation)
```

Governance validators, all PASS, re-run after the fixes:

```
backend/.venv/bin/python knowledge/00-System/verify_baselines.py            -> PASS, 4/4
backend/.venv/bin/python knowledge/00-System/validate_capabilities.py       -> PASS, 7/7 APPROVED
backend/.venv/bin/python knowledge/05-QA/tools/capability_drift_check.py    -> PASS, 8/8, no drift
backend/.venv/bin/python tools/validate_repo_skeleton.py                    -> PASS, 7/7
backend/.venv/bin/python tools/validate_architecture_gates.py --gate module-deps
                                                                             -> GATE_NOT_IMPLEMENTED (unchanged, correct — R04 untouched)
backend/.venv/bin/python tools/validate_migration_ordering.py              -> PASS (no records yet)
backend/.venv/bin/python tools/validate_baseline_binding.py                -> PASS, 4/4
backend/.venv/bin/python tools/validate_capability_manifest.py --manifest knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml
                                                                             -> PASS, 9/9
backend/.venv/bin/python knowledge/05-QA/tools/run_regression.py           -> AGGREGATE PASS (4/4, 1 N/A for retired CAP-007)
git diff --check -- backend/app/modules backend/tests/contract            -> clean
```

## Independent negative-case drill (this session, own repeat, throwaway copy)

Before the review, this session ran its own version of the same drill
(copy of `backend/app` + `backend/tests/{harness,contract}` to `/tmp`,
outside the real tree): the unmodified copy passed; breaking `payment`'s
assertion made `test_all_six_domain_scaffolds_pass` fail with
`{'payment': 'failed'}` in the raised `AssertionError`; deleting
`payment`'s file made `test_all_six_domain_scaffold_paths_exist` fail
naming `['payment']` as missing, with the second test reporting all six
as `NOT_COLLECTED` (the same intentional-conservative behavior noted
above). The `/tmp` copy was deleted immediately after each check; `git
status` on the real tree was confirmed unchanged throughout (only the
intended new files ever appeared as untracked/modified).

## What this slice does NOT claim

- Does not claim SCN-MOD001-132 or SCN-MOD001-133 as PASS/promoted. Both
  are Blocker-tier, routed (in full or in part) to
  `veyro-security-reviewer`/Opus — a code review, even a clean one, is a
  distinct gate from the security review their own routing requires. That
  review has not run.
- **Post-session correction:** the earlier assertion that this ACPX Claude Code route produced no verifiable transcript was false. The orchestrator found both JSONL traces and independently ran `mr_verify.py`: implementation lead 150/150 `claude-sonnet-5` turns, internal `veyro-code-reviewer` 35/35 `claude-opus-5-5` turns, both PASS without fallback. The code review remains BLOCKED on the pre-fix version; attestation does not turn it into approval. Transcripts: `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/1bba8cd1-c383-477f-8d41-195fb71de236.jsonl` and `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/1bba8cd1-c383-477f-8d41-195fb71de236/subagents/agent-a4018a8a551393f5c.jsonl`.
- Does not touch R04, SCN-067, BUG-048, or ADR-010 — all remain exactly as
  `CURRENT_STATE.md`/`CURRENT_HANDOFF.md` recorded them before this
  slice.
- Does not commit or push. All new files remain untracked working-tree
  additions pending the still-outstanding Slice 5 harness commit this
  slice's own files depend on (P2 finding 5 above).

## Round 2 — independent security review found NF-1/NF-2/NF-3, remediated

A fresh-context `veyro-security-reviewer` (Opus, transcript-attested PASS
97/97 `claude-opus-5-5`, no participation in implementation or the round-1
code review) ran this slice's SCN-132/133 drill and mutant set against
the round-1 fixed version:
`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT-SECURITY-REVIEW-2026-10-03.md`.
**Verdict: BLOCKED, P0=0/P1=1/P2=3/P3=3.**

- **NF-1 (P1):** the round-1 `__post_init__` validated positivity but not
  finiteness or `Side` membership. `Decimal("Infinity")` legs, or any
  `side` that wasn't a real `Side` member (`"debit"` string, `None`, a
  foreign enum), were silently excluded from both sums — a false clean,
  including the reviewer's own SCN-133 negative case expressed as
  `side="debit"`.
- **NF-2 (P2):** the round-1 fix had zero regression tests; 7 of the
  reviewer's 12 adversarial mutants survived, including one reverting to
  the exact round-1 counterexample.
- **NF-3 (P2, SCN-132):** `test_domain_scaffold_inventory.py`'s junit
  parsing was last-write-wins per domain, so a skipped
  `test_scaffold_live` followed by a differently-named passing sibling
  test in the same file masked the skip — order-dependent, confirmed with
  both e1/e2 orderings.
- NF-4 (P2): `CURRENT_STATE.md`/`CURRENT_HANDOFF.md` still falsely denied
  any `mr_verify.py` transcript for a Claude Code session, contradicting
  this slice's own already-corrected note above. NF-5/NF-6/NF-7 (P3):
  documentation-accuracy and disclosed-limitation findings.

**Remediation this session (fixed, not yet re-reviewed):**
- `backend/tests/contract/test_financial_invariant_scaffold.py`:
  `__post_init__` now raises `TypeError` for a non-`Side` `side` or a
  non-`Decimal` amount, and `ValueError` for a non-finite or non-positive
  amount — closing both NF-1 paths. Added regression tests for the
  unmatched-credit case, zero/negative/NaN/±Infinity amounts, four
  non-`Side` `side` shapes, and a non-empty assertion on the balanced
  fixture — closing NF-2.
- `backend/tests/contract/test_domain_scaffold_inventory.py`:
  `_parse_junit` now counts only testcases literally named
  `test_scaffold_live`, requires exactly one per domain, and never lets a
  later testcase overwrite an earlier one for the same domain — closing
  NF-3. Docstring corrected to state this precisely (also closes NF-5's
  overstatement) and discloses the NF-7 content-blindness limitation
  without building a second truth source.
- `CURRENT_STATE.md`/`CURRENT_HANDOFF.md`: the false "no `mr_verify.py`
  transcript" lines corrected with the real re-run results (closing
  NF-4). `BUG_REGISTRY.md`'s trailing blank line at EOF removed, making
  the unscoped `git diff --check` genuinely clean (closing NF-6).
- Independently re-verified, all real execution: `ruff check .` and
  `mypy app tests` clean; full suite 184/184 passing (174 + 10 new);
  direct six-domain run 6/6; all 8 governance validators PASS; aggregate
  `run_regression.py` PASS 4/4 (1 N/A); unscoped `git diff --check` clean.
- Independently re-drilled in throwaway `/tmp` copies, not the live tree:
  NF-1's listed adversarial cases (Infinity, non-`Side` sides) now reject
  at construction; the reviewer's mutants M2, M4, M6, M11, M12 are now
  killed by the new regression tests (M3 still survives, matching the
  reviewer's own note that it's equivalent while the positivity check
  holds — not a real gap); NF-3's e1 and e2 order variants both now
  correctly fail, naming the masked domain regardless of definition
  order.

**Still not closed.** BUG-050 stays OPEN (round 2) — this remediation has
not itself had an independent review. SCN-MOD001-132/133 remain
unpromoted.

## Round 3 — independent re-review confirmed round 2, found one precision gap

A third fresh-context `veyro-security-reviewer` (Opus, transcript-attested
PASS 92/92 `claude-opus-5`, distinct agentId from both prior reviewers)
independently re-executed round 2's full drill set — plus two new
sibling-ordering variants it added itself (e3, e4) — and the full mutant
set against the round-2 code:
`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT-SECURITY-REVIEW-ROUND3-2026-10-03.md`.
**Verdict: BLOCKED, P0=0/P1=0/P2=1/P3=2.**

It confirmed NF-1 through NF-6 genuinely fixed by re-running them, not by
reading the round-2 record, and found:

- **NR3-1 (P2):** the round-2 fix validated finiteness and `Side`
  membership but not decimal *precision*. `sum()` runs under the default
  28-significant-digit context, which silently rounds a small leg into a
  much larger one on the same side — e.g. `Dr 1E+30 + Dr 0.01` vs
  `Cr 1E+30` reported balanced, hiding the unmatched 0.01 debit. Same
  false-clean class as BUG-050/NF-1, one precision level deeper; round
  2's own recommended fix (finiteness + type + `Side` checks) was
  implemented correctly and completely — this is a gap in that
  recommendation, not implementer non-compliance.
- **NR3-2 (P3):** the `isinstance(amount, Decimal)` guard itself had no
  regression test; mutant M14 (drop that one guard) survived. It still
  failed closed, but by accident (`AttributeError` from `is_finite()` on
  a non-`Decimal`), not by design.
- **NR3-3 (P3):** round 2's own new `test_unmatched_credit_fails_closed`
  line was 103 characters, regressing `ruff format --check` on this file
  (round 2's P2-4 had recorded "FIXED for all 25 Slice-7 files"). `ruff
  check` stayed clean throughout; the evidence wording didn't separate
  the two claims.

**Round-3 remediation (same session, re-verified, not yet re-reviewed):**
- `assert_debits_equal_credits` now computes both sums inside
  `decimal.localcontext()` with `Inexact` trapped, catching the trap and
  re-raising as a named `DEBITS_NE_CREDITS` `FinancialInvariantViolation`
  — closing NR3-1. **Corrected 2026-10-03, round 7 (NR7-1, claim 1): both
  parts are stale. The precision route has raised the distinct
  `DEBITS_CREDITS_UNEVALUABLE_PRECISION` code since round 4's own
  remediation, not `DEBITS_NE_CREDITS` — see round 7's N1/N2/N3 probes,
  all `VIOLATION[PRECISION-TRAP]`. And "closing NR3-1" is the exact
  phrasing round 4 itself flagged as overclaiming: NR3-1's regression
  lock was only half-complete until round 4's NR4-1 fix (corrected in
  `BUG-050…md` and `CURRENT_STATE.md`, not here until now).**
- Added regression tests for the reviewer's exact `1E+30`/29-significant-
  digit counterexamples, plus a boundary test confirming a sum that fits
  exactly within the 28-digit precision is still compared normally (not
  treated as a precision failure). **Corrected 2026-10-03, round 7
  (NR7-1, claim 2): this is verbatim the NR4-2 claim the test as written
  could not confirm — both failure routes shared one error code at the
  time, so the test could not discriminate them. Round 7 reconstructed
  round 4's actual state (`T6 + T10a + T10b`, both of round 5's fixes
  undone) and it SURVIVES — 19 passed, exit 0, 1 passed with the
  boundary test in isolation — the direct refutation. Round 5's fix,
  not round 4's, is what made this claim true; see `BUG-050…md`'s
  round-3 and round-5 sections.**
- Added two parametrize rows (`float`, `int` amounts) to the existing
  construction-rejection test, killing mutant M14 — closing NR3-2.
- Ran `ruff format` on the file; `ruff format --check` on the two
  Slice-7 contract files confirmed clean — closing NR3-3's formatter
  half. This record and `BUG-050`'s own file now state `ruff check` and
  `ruff format --check` as separate claims going forward.
- Independently re-verified, all real execution: full suite 189/189
  passing (184 + 5 new), `ruff check` clean, `ruff format --check` clean
  on the Slice-7 files, mypy strict clean (47 source files), all
  governance validators + aggregate regression PASS.
- Independently re-drilled in a throwaway `/tmp` copy, not the live tree:
  the reviewer's exact N1 (`1E+1000`), N2 (`1E+30`/`0.01`), and N3
  (29-significant-digit) counterexamples now all raise
  `DEBITS_NE_CREDITS`; **corrected 2026-10-03, round 7 (NR7-1, claim 3):
  false for current code, independently of when it was written. Round 7's
  N1/N2/N3 probes all raise the distinct `DEBITS_CREDITS_UNEVALUABLE_PRECISION`
  code (round 4's own remediation gave the precision route that code).
  This is the same claim class round 6 identified and corrected in
  `CURRENT_HANDOFF.md`/`CURRENT_STATE.md` as "now raise `DEBITS_NE_CREDITS`"
  — this record's "now **all** raise" phrasing was the sixth location
  that survived round 6's own grep patterns.** the 28-digit boundary case
  still compares normally (reports the real mismatch, not a precision
  trap); **note, round 7: this clause is true of current code (round 7's
  boundary probe is `VIOLATION[COMPARISON]`), but was not a valid
  verification claim at round 3, the same way claim 2 above was not —
  recorded for completeness, not because its content is wrong today.**
  the 40-leg `0.01` accumulation and the plain `100.00`/`25.50` fixture
  both still pass unaffected; mutant M14 now fails the suite (killed)
  when applied to the copy.

**Still not closed.** BUG-050 stays OPEN (round 3) — this remediation has
not itself had an independent review. Per round 3's own note, SCN-132 has
no blocking finding of its own, but whether to promote it separately
while BUG-050 (filed against the shared financial-invariant file) stays
open for SCN-133 is the orchestrator's call, not self-decided here.
SCN-133 remains unpromoted.

## Next legally allowed action

A fresh round-4 `veyro-security-reviewer` (Opus) re-review that re-runs
round 3's own drill set (including e3/e4 and the N1/N2/N3 precision
probes) and full mutant set (including M13-M15) against the round-3
code. Only that review (not this record, not any prior review) may move
either scenario's status or close BUG-050. Until then, this slice is
implemented-and-reviewed-three-times, not promoted.

**Corrected 2026-10-03, round 9 (NR9-1): the above is round 3's own
closing text and is five rounds stale — rounds 4 through 9 have since
run (see the front matter's round-9 correction above and
`BUG-050…md` for the full chain). As of this round's remediation, the
slice has been implemented-and-reviewed-nine-times, still not promoted.
The current next legally allowed action is a fresh round-10
`veyro-security-reviewer`/Opus re-review that: (i) verifies this
record's three NR9-1 corrections and NR9-2's four OBS-6 overclaim
corrections; (ii) re-derives the mutant proof that the AST-based
`test_match_assertions_use_only_the_shared_constants` (NR9-3) actually
kills F1-F5 and passes a benign multi-line reformat, rather than
trusting this session's own report of having done so; (iii) re-runs the
broadened derivation query (NR9-4) and checks the bucket-count
prediction holds; and (iv) re-runs the full drill/mutant/probe/fuzz set
against this round's remediation. Only that review — not this record,
not any prior round's record, not the session that wrote this
correction — may close BUG-050 or promote either scenario.**

---
doc: GOV-01-R02 Slice-7 domain scaffolds + financial-invariant harness — INDEPENDENT SECURITY RE-REVIEW, ROUND 9
module: MOD-001
scenarios: SCN-MOD001-132, SCN-MOD001-133
bug: BUG-050 (OPEN)
round: 9
date: 2026-10-03
verdict: BLOCKED — P0=0 / P1=0 / P2=2 / P3=2
reviewer: veyro-security-reviewer (fresh context; did not implement, code-review, or security-review any prior round of this slice)
orchestrator: Sonnet session performing independent transcript/model-identity attestation and mechanical cross-verification only — per this round's explicit dispatch constraint, the orchestrating session did not itself issue the security judgment below.
---

# Round-9 independent security re-review — GOV-01-R02 Slice 7

## 0. Dispatch constraint for this round (differs from rounds 2-8)

Rounds 2 through 8 each self-remediated their own findings in the same
session. Round 9 was explicitly dispatched **not** to self-remediate: no
source file edit, no `BUG-050`/`STATUS.md`/`TEST_RESULTS.md`/
`CURRENT_STATE.md`/`CURRENT_HANDOFF.md`/`BUG_REGISTRY.md` update, no
scenario promotion, no commit/push. The fresh-context `veyro-security-reviewer`
subagent (Opus) performed the full independent review below and returned
its findings as text rather than writing this file itself — its agent
definition grants `Read, Grep, Glob, Bash` only, no `Write`/`Edit`. This
file is written by the orchestrating Sonnet session, verbatim from the
subagent's returned report, with one added section (§1, below) recording
the orchestrator's own independent transcript-identity attestation and a
second added section (§13) recording the orchestrator's own independent
mechanical cross-verification. The orchestrator did not re-derive, second-guess,
or adjust the subagent's findings or verdict.

## 1. Session and model identity — independently attested by the orchestrator

| Item | Value |
|---|---|
| Agent type | `veyro-security-reviewer` |
| agentId | `a9e9c30d3ecc209ab` (distinct from all eight prior reviewers) |
| Transcript path | `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/8f94d087-fcd3-4623-81a0-27b18c1a109f/subagents/agent-a9e9c30d3ecc209ab.jsonl` |
| Meta path | `…/subagents/agent-a9e9c30d3ecc209ab.meta.json` |
| `.meta.json` contents (verbatim) | `{"agentType":"veyro-security-reviewer","description":"GOV-01-R02 Slice-7 round-9 independent security review","toolUseId":"toolu_01QY7EkwrC6ocahwWrEmfZ9V","spawnDepth":1,"requestShape":"background","requestNonInteractive":true,"model":"opus"}` |
| `mr_verify.py` result (run by the orchestrator against the real `subagents/agent-*.jsonl` transcript, not the task-output buffer and not the `.meta.json` self-report alone) | `{"verdict": "PASS", "reason": "114 turn(s), 100% consistent, model 'claude-opus-5' matches required tier 'opus'.", "models_observed": ["claude-opus-5"], "expected_tier": "opus"}` — exit 0 |
| Spawn depth | 1 |
| Provider/model-assurance failure? | **No.** `mr_verify.py` returned PASS, not `BLOCKED: MODEL_ASSURANCE_UNVERIFIED`. No fallback/substitution occurred; all 114 assistant turns carry the identical, DC-17-qualified `claude-opus-5` id. |

The orchestrator located the real transcript by searching
`~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/` for the agentId
reported in the task-completion notification, found it at the path
above (distinct from the task's own `/private/tmp/.../tasks/<id>.output`
buffer, which is JSON-shaped but is not the harness's per-turn
`assistant`-role transcript `mr_verify.py` is built to read), and ran
`backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <path> opus
veyro-security-reviewer` directly. This satisfies this round's dispatch
requirement to independently attest the actual subagent transcript's
per-turn resolved model identity and agent ID, not merely the `model:
opus` dispatch parameter or the agent definition's declared tier.

## 2. Verdict

**BLOCKED — P0=0 / P1=0 / P2=2 / P3=2.**

Zero false cleans for the fifth consecutive round. Both P2s are
record-accuracy/claim-accuracy gaps, not product defects — but one
(NR9-2) is a *detection-completeness overclaim*, a stronger species than
rounds 7-8's pure staleness findings: it is not that a number went
stale, but that four durable records (including the test's own
docstring) describe the new OBS-6 self-check as asserting a universal
property it does not, in fact, enforce.

## 3. Re-derived document set (mechanical)

`rg -l 'BUG-050|test_financial_invariant_scaffold|SCN-MOD001-133'
knowledge .claude | sort` → **19 files**, all under `knowledge/`;
`.claude/` contributes zero hits. The reviewer's independent triage
reproduces round 8's 8/1/10 split exactly (8 live + 1 plan + 10 dated =
19):

- **Live (8):** `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`,
  `BUG_REGISTRY.md`, `MOD-001/STATUS.md`, `MOD-001/TEST_RESULTS.md`,
  `MOD-001/SCENARIOS.md`, `BUG-050-financial-invariant-placeholder-false-clean.md`,
  the Slice-7 implementation record.
- **Plan (1):** `MOD-001/IMPLEMENTATION.md` — one hit, a directory-tree
  comment, confirmed not a state claim.
- **Dated (10):** the 7 review reports (round 2 + ROUND3-ROUND8) plus
  `SLICE-7-PROVIDER-LIMIT-CHECKPOINT-2026-10-03.md`,
  `CR-MOD001-GOV01-R02-DOMAIN-SCAFFOLDS-2026-10-03.md`,
  `ROUTING_DRILL_2026-09-18-mr-evidence-backfill.md`.

All 8 live documents were re-read against today's executed evidence.
Seven are current and internally consistent. The eighth is NR9-1 (§5).

## 4. NR8-1 and the round-7→8 correction chain — re-audited

`TEST_RESULTS.md` was genuinely corrected, not merely narrated: line 11
now reports 194/194 and 24/24 (matching the reviewer's own measurement),
carries round 8's `BLOCKED P0=0/P1=0/P2=1/P3=0`, and preserves the
round-2 `184/184`/`14/14` text as an explicitly-labelled historical
checkpoint. `STATUS.md`, `BUG_REGISTRY.md` (row + front matter),
`CURRENT_STATE.md` and `CURRENT_HANDOFF.md` are all consistent at round
8. Round 8's own report text ("18 files... ten sit outside the
eight-document list") is internally consistent as of its own run-time
(the ROUND8 report did not yet exist when it ran its query); BUG-050's
round-8 paragraph correctly reconciles this to 19 with the 8/1/10 split,
matching this round's re-run exactly. No residual inconsistency, except
the off-by-one noted in NR9-4.

## 5. Findings

### NR9-1 (P2) — a tenth location: the Slice-7 implementation record is five rounds stale in three present-tense places

`knowledge/03-Modules/MOD-001/evidence/implementation/SLICE-7-gov01-r02-domain-suite-scaffolds-financial-invariant-2026-10-03.md`
is one of the 8 documents BUG-050's own round-8 paragraph lists as
carrying "live, present-tense current-state claims… kept current every
round." It is not. Round 7's NR7-1 fix corrected four claims *inside the
round-3 section body only*; round 8 did not re-read the file, having
inherited "NR7-1 closed."

Three stale present-tense locations, all five rounds behind:

- Front matter `independent_review:` enumerates rounds 1, 2 and 3 only.
  Rounds 4-8 exist.
- Front matter `status:` — "IMPLEMENTED, fixed-after-review (**three
  rounds**), NOT PROMOTED… round 3 is that gate's third pass, still
  BLOCKED (**now** P2=1/P3=2, down from P1=1 originally)." The word "now"
  is explicitly present-tense; the current verdict is round 8's
  `P0=0/P1=0/P2=1/P3=0`.
- Body §"Next legally allowed action" — "A fresh **round-4**
  `veyro-security-reviewer` … against the **round-3** code… Until then,
  this slice is implemented-and-reviewed-**three-times**, not
  promoted." Every other live document's equivalent section was
  rewritten each round; this one never was.

Identical sentence-shape to NR7-2 (`STATUS.md`) and NR8-1
(`TEST_RESULTS.md`). Severity P2 for consistency with those two.

### NR9-2 (P2) — the OBS-6 self-check's documented claim is materially stronger than what it enforces

Four durable locations state the new test asserts a universal property.
Measured, it does not. Exact wordings cited: `CURRENT_STATE.md:36`
("asserts **every** `match=` call site uses a shared constant"),
`CURRENT_HANDOFF.md:32` ("…**every**…"), `BUG-050…md:160` ("…**never an
inline literal**"), and the test's own docstring,
`test_financial_invariant_scaffold.py:296-298` ("…**every**… never an
inline literal.").

The regex is
`r"pytest\.raises\(FinancialInvariantViolation,\s*match=(_\w+|r?\"[^\"]*\")\)"`.
Executed, as a fifth added call site carrying an unanchored literal:

| Variant | Result |
|---|---|
| F1 `match='DEBITS_NE_CREDITS'` (single quotes) | **SURVIVED** — 23 passed, exit 0 |
| F2 `match="DEBITS_NE_CREDITS"` (double quotes) | KILLED (count assertion) |
| F3 multi-line call with trailing comma | **SURVIVED** — 23 passed, exit 0 |
| F4 `match=SNEAKY` (no leading underscore) | **SURVIVED** — 23 passed, exit 0 |
| F5 `match=f"DEBITS_NE_CREDITS"` (f-string) | **SURVIVED** — 23 passed, exit 0 |

Four of five escape both assertions — the count still reads exactly 4,
so the test does not register that a fifth call site exists. Round 8
verified only the one variant it had itself named (F2). This is
structurally the same pattern as NR5-2: a remediation record asserting
a general property from a single-variant check. P2 matches
NR5-2/NR7-2/NR8-1.

### NR9-3 (P3) — the self-check is coupled to one exact source formatting, and the project's own blocking formatter produces the escaping shape

Executed in a throwaway copy: a realistic new negative test using the
*correct* shared constant, on a line exceeding `line-length = 100`,
passed through the project's own `ruff format` (a blocking CI gate per
`IMPLEMENTATION.md` §3). Ruff rewrote it onto a new line
(`with pytest.raises(\n        FinancialInvariantViolation,
match=_COMPARISON_MATCH\n    ):`), which the regex does not match.
Result: 23 passed, the fifth call site wholly invisible to the
self-check. Conversely, a benign multi-line reformat of an *existing*
call site (constant preserved) **fails** the self-check — it is both
under- and over-sensitive, and the natural "fix" (lowering the expected
count from 4 to 3) permanently removes that site from the check. No
reachable false clean in `assert_debits_equal_credits` itself —
`test_error_codes_are_mutually_disjoint` uses no `match=` and cannot be
weakened by any `match=` edit — which is why this is P3, not higher. A
`ast`-based structural check would close it and be formatting-immune.

### NR9-4 (P3) — two defects in the recorded derivation procedure itself

- The recorded query tokens
  (`BUG-050|test_financial_invariant_scaffold|SCN-MOD001-133`) omit
  `SCN-MOD001-132` (the other half of this slice) and
  `test_domain_scaffold_inventory` (the other file BUG-050 is filed
  against). A broadened query returns 29 files (10 more); all 10
  triaged — 9 are pre-existing unrelated hits on a `test_scaffold_live.py`
  filename collision or an archived chunk narrative, zero are new
  live-claim documents. Cost nothing this round; round 10 inherits the
  narrow query as the control. **Corrected 2026-10-03, round 10 (NR10-3):
  the "9 pre-existing unrelated hits on a `test_scaffold_live.py` filename
  collision" sentence above is the tell — the query actually run here
  included a third token (`test_scaffold_live`) beyond the two named at
  the top of this bullet, which is why it measured a 10-file delta
  (29 total) that the retained implementation session's own 5-token
  reproduction (naming only the two tokens above) could not match,
  disclosed as an unresolved discrepancy in `BUG-050…md`'s round-9
  section. Round 10 adopts the 6-token query (adding `test_scaffold_live`
  explicitly) as the new recorded baseline for round 11 — see
  `BUG-050…md`'s round-10 section.**
- BUG-050 line 159 predicts round 9's review-report bucket will be 8
  "since this round's own report is now part of it" — measured before
  this report existed, the bucket was 7, exactly as line 157 states; it
  reaches 8 only once this file exists. Off by one.

## 6. Mutants and structural tests (all reconstructed from prose, no diff read)

Reconstructed in a throwaway `/tmp` copy of `backend/` (Slice-7 file
SHA-256 `bc4f2f129d2a14daaafaf59959b45cbffac5a777edc603245874877c1a5706c5`,
confirmed byte-identical to the real tree — see §13). Baseline 22/22 on
the copy.

| Mutant | Reconstruction | Result |
|---|---|---|
| **T6** | insert `ctx.prec = 27` after `ctx.traps[Inexact] = True` | **KILLED** — 1 failed: `test_precision_boundary_within_context_still_compares_exactly` |
| **T11** | precision route's message re-prefixed `DEBITS_NE_CREDITS:` with the precision code as a parenthetical aside | **KILLED** — 5 failed (two independent kill paths: `test_precision_loss_fails_closed[legs0-3]` + `test_error_codes_are_mutually_disjoint`) |
| OBS-4a-i/ii | de-anchor `_COMPARISON_MATCH` / `_PRECISION_MATCH` | **KILLED** both — `test_all_match_assertions_are_anchored` |
| OBS-4b-i/ii | embed each route's code in the other's message | **KILLED** both — `test_error_codes_are_mutually_disjoint` |
| OBS-6/C1 | re-inline unanchored double-quoted literal at call site 1 | **KILLED** — `test_match_assertions_use_only_the_shared_constants` (genuinely discriminates the exact mutant that survived round 8) |
| M-BUG050 | revert to signed net sum vs zero | **KILLED** (3) |
| M4 / M6 | one-directional comparison / `<=`→`<` | **KILLED** (1 / 1) |
| M-finite / M-side / M-dec | drop each `__post_init__` guard | **KILLED** (2 / 3 / 2) |
| T5 / T7 / T-noTrap | bump precision / trap debit side only / remove trap | **KILLED** (5 / 1 / 5) |
| M-eq | `leg.side is Side.DEBIT` → `==` | **SURVIVED — true algebraic equivalent, no finding** (same species as NR6-3's M1; proved by execution that `Enum.__eq__` plus the construction-time `isinstance` guard make this non-exploitable) |

Regex census: 11 raw `pytest.raises` occurrences, 3 in docstrings, 8 real
call sites, exactly 4 carrying `match=` (lines 139, 151, 227, 247; three
`_COMPARISON_MATCH`, one `_PRECISION_MATCH`), zero inline literals, zero
docstring false hits. Round 8's census is accurate.

## 7. Differential fuzz — 45,000 cases, generator written this round

Exact `Fraction` oracle; stratified over five amount families (2dp
money, wide exponents, 25-32-digit tails, `1E+26`-`1E+34` coincidences,
sub-`1E-20` tinies), 1-12 legs, ~45% forced to exact balance.

- Stratum A (seed `202610039`, 30,000 cases): 4,107 correct clean ·
  5,474 correct `DEBITS_NE_CREDITS` · 9,460 unevaluable-precision on
  balanced sets (by design, NR4-3) · 10,959 on unbalanced sets
  (fail-closed) · **0 false cleans · 0 false violations · 0 raw
  exceptions**.
- Stratum B, money-only (seed `202610039991`, 15,000 cases): 6,660
  correct clean · 8,340 correct violations · **0 precision over-fires ·
  0 false cleans · 0 false violations · 0 raw exceptions** — confirms
  NR4-3's resolution holds for realistic shapes.

## 8. CAP-008 live fixture binding — CONFIRMED LIVE AND REACHABLE

Colima 0.10.3 / Lima 2.2.0 / Docker Engine (in-VM) 29.5.2 / Docker CLI
29.6.0 at the pinned realpath — exactly the `APPROVED_ENGINE` tuple and
`TRUSTED_DOCKER_CLI_*` constants in `postgres.py`, and exactly the
CAP-008 registry row (`review_status: APPROVED`, `next_review_due:
2026-12-31`, not past due).

**The six domain scaffolds ran for real: 6/6 PASSED.** A direct probe
of `disposable_postgres()` captured a genuinely live container
(`veyro-mod001-harness-48d34910`, published `127.0.0.1:33502->5432/tcp`,
`select version()` → `PostgreSQL 16.15`, pinned image digest confirmed)
with zero leftovers after context exit. Fail-closed drills: unreachable
`DOCKER_HOST` and Docker Desktop's own socket path both produced a clean
`RuntimeError`, no mock/fallback. Docker Desktop was deliberately not
started (would activate an unapproved capability). Secrets: runtime
password via `secrets.token_urlsafe(24)`, passed by valueless `-e`, kept
out of error strings; a credential-shaped-value scan across all nine
Slice-7 files returned zero hits. Synthetic fixtures only; no spend, no
real member data.

## 9. Scenario acceptance criteria

**SCN-MOD001-133 — MET on both legs, executed.** Positive:
`test_balanced_synthetic_entries_pass` PASSED. Negative: unbalanced set
raises `FinancialInvariantViolation: DEBITS_NE_CREDITS: total debits
135.50 != total credits 125.50 across 5 leg(s)` — naming the specific
invariant, both totals, and the leg count.

**SCN-MOD001-132 — MET, including the negative case, executed in a
throwaway copy.** Positive: 6/6 against live disposable Postgres.
Negative drills (delete/rename/break one domain's scaffold; both
skip/sibling orderings e1/e2; a shadowed-duplicate variant e3) all exit
non-zero via `test_domain_scaffold_inventory.py`, each naming the
specific broken domain, order-independent. Noted: the *raw* six-path
pytest run alone exits 0 on a skipped scaffold ("6 passed, 1 skipped");
the protection is the inventory contract test, which is inside
`testpaths = ["tests"]` and does run in the default 194-test suite — but
the guarantee rests wholly on that contract test remaining there. A
differently-scoped invocation (`pytest app/modules` directly, excluded
from `testpaths`) was confirmed to silently report green with one domain
deleted; the committed design avoids this via `testpaths` scoping plus
the inventory test, not by making that alternate invocation itself safe.

## 10. Routine validators — exact results (reviewer's run)

| Check | Result |
|---|---|
| Full backend suite | **194 passed** (re-run at close: 194 passed) |
| Focused contract tests (financial-invariant + domain-scaffold-inventory) | **24 passed** |
| `test_financial_invariant_scaffold.py` alone | **22 passed** |
| Six domain scaffolds | **6 passed** |
| `ruff check --no-cache .` (from `backend/`) | All checks passed, exit 0 |
| `ruff format --check` (Slice-7 files) | 2 files already formatted |
| `ruff format --check` (six scaffolds + conftest) | 7 files already formatted |
| `ruff format --check --no-cache .` (repo root) | 7 would be reformatted — same pre-existing non-Slice-7 set rounds 2-8 recorded, zero Slice-7 files |
| `mypy app tests` (strict) | Success: no issues found in 47 source files |
| `verify_baselines.py` / `validate_capabilities.py` / `capability_drift_check.py` / `validate_repo_skeleton.py` / `validate_baseline_binding.py` / `validate_migration_ordering.py` / both `validate_capability_manifest.py` manifests / `evidence_integrity_check.py` | All PASS |
| `run_regression.py` | AGGREGATE PASS 4/4 (1 N/A: retired CAP-007) |
| `git diff --check` (unscoped) | clean, exit 0 |

## 11. Observations (not findings)

- **OBS-8** — the Python runtime toolchain (`psycopg`, `pytest`, `ruff`,
  `mypy`) has no `CAPABILITY_REGISTRY.md` row — hash-pinned via
  `requirements-dev.lock.txt`, but unregistered/unqualified in the same
  sense BUG-038 rated Docker/Postgres P1. Not a Slice-7 finding (predates
  it, affects the whole backend) — flagged for orchestrator triage, not
  to block this slice.
- **OBS-9** — `.claude/` contributes zero hits to the derivation query;
  recorded so a future round does not assume it was meaningfully
  exercised.
- **OBS-10** — `run_regression.py` writes an untracked run-record file
  into the repo as designed behavior; a "reviewer touched nothing" claim
  needs this carve-out.
- **OBS-11** — three procedure traps: the `importlib`/`sys.modules`
  registration trap (OBS-7c) is real; the six domain scaffolds are *not*
  in the default `pytest` collection (`testpaths = ["tests"]`) and must
  be invoked explicitly, easy to misread as already covered;
  `validate_capability_manifest.py` requires `--manifest` or exits 2
  with an argparse usage error that could be mistaken for a validator
  failure.
- **OBS-12** — the reviewer's scratch directory was deleted per this
  round's dispatch constraint, contrary to rounds 5-8's convention of
  preserving it for the next round. Every mutant above is fully
  specified in prose and reconstructible from it; the orchestrator
  should reconcile these two conventions before round 10.

## 12. Scope boundaries honored

No fix implemented; no source file edited (hash-confirmed, §13). BUG-050
not closed. Neither scenario promoted or edited. No other `.md` written
by the subagent. All mutation work in a throwaway `/tmp` copy, deleted;
zero leftover `veyro-mod001-harness-*` containers. R04, ADR-010
Amendment A2, BUG-048 and SCN-MOD001-067 were not read into, commented
on, or acted upon. No commit, push, spend, real member data, deploy, or
configuration change.

## 13. Orchestrator's independent mechanical cross-verification

Run by the orchestrating Sonnet session, after the subagent's
completion, against the live tree (not inherited from the subagent's
report):

| Check | Orchestrator's own result | Matches subagent's claim? |
|---|---|---|
| `backend/.venv/bin/python -m pytest -q` (full suite) | **194 passed** in 22.83s | Yes |
| `ruff check --no-cache .` (from `backend/`) | All checks passed! | Yes |
| `ruff format --check` on both Slice-7 files | 2 files already formatted | Yes |
| `mypy app tests` (strict) | Success: no issues found in 47 source files | Yes |
| SHA-256 of `tests/contract/test_financial_invariant_scaffold.py` | `bc4f2f129d2a14daaafaf59959b45cbffac5a777edc603245874877c1a5706c5` | Yes — matches the hash the subagent recorded; confirms the file was not edited this round |
| `git diff --check` (unscoped, repo root) | clean, exit 0 | Yes |
| `git rev-parse HEAD` | `e516bedabf3d654ad3ae16d948b8f3522739ddc2` | Yes — HEAD unchanged |
| `git status --short` | Identical pre-existing uncommitted working-tree state from before this round's dispatch (no new files, no new modifications attributable to this round) | Confirms no implementation fixes were made |
| `docker ps -a` | No `veyro-mod001-harness-*` or other Slice-7-drill container present | Confirms no leftover containers |
| `mr_verify.py` against the real subagent transcript | PASS, 114/114 `claude-opus-5` (§1) | Independently attested, not merely re-stated |

The orchestrator did not re-run the mutant reconstructions, the fuzz, or
the CAP-008 live-container probe itself (that is the Opus-reserved
judgment work this round explicitly delegates), and did not re-derive or
second-guess the P0-P3 verdict. All mechanical/routine checks the
orchestrator did re-run independently reproduce the subagent's reported
results exactly.

## 14. Closure assessment and next action (subagent's own, unmodified)

**BUG-050 is behaviourally closeable and record-wise not yet.** Five
consecutive rounds of zero false cleans; 20 mutants killed this round
including both historically decisive ones (T6, T11) and the original
defect shape; the one survivor is a proved true equivalent. Both
scenarios' acceptance criteria are met on real execution. What remains
is the same record/claim-accuracy class that has now run eight rounds
unbroken — and NR9-2 shows it has migrated from "a document reports
stale numbers" to "a document reports a detection guarantee the test
does not provide," a more consequential form. The closure decision is
explicitly not the reviewer's or the orchestrator's to make this round.

**Next legally allowed action for round 10:** a fresh
`veyro-security-reviewer`/Opus session that (i) corrects NR9-1's three
present-tense locations in the Slice-7 implementation record and
NR9-2's four overclaim locations, (ii) replaces the OBS-6 regex
self-check with a formatting-immune `ast`-based equivalent and proves it
kills F1-F5 while passing a benign multi-line reformat, (iii) broadens
the recorded derivation query to include `SCN-MOD001-132` and
`test_domain_scaffold_inventory` and corrects the off-by-one bucket
prediction, and (iv) re-runs the full drill/mutant/probe/fuzz set
against that remediation — before BUG-050 is closed or either scenario
promoted. R04/SCN-067/BUG-048/ADR-010 Amendment A2 remain separately
BLOCKED on the unrelated Anthropic model-assurance safeguard, entirely
untouched by this round.

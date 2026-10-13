---
doc: GOV-01-R02 Slice-7 domain scaffolds + financial-invariant harness — INDEPENDENT SECURITY RE-REVIEW, ROUND 5
module: MOD-001
scenarios: SCN-MOD001-132, SCN-MOD001-133
bug: BUG-050 (OPEN)
round: 5
date: 2026-10-03
verdict: BLOCKED — P0=0 / P1=0 / P2=1 / P3=1
reviewer: veyro-security-reviewer (fresh context; did not implement, code-review, or security-review any prior round of this slice)
---

# Round-5 independent security re-review — GOV-01-R02 Slice 7

## 1. Session and model identity (reported plainly, not asserted)

| Item | Value |
|---|---|
| Agent type | `veyro-security-reviewer` |
| agentId | `agent-ab26f08ded3cc79eb` (distinct from all four prior reviewers) |
| Transcript path | `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/e581c15c-c478-49b9-af2b-891b8b8ff654/subagents/agent-ab26f08ded3cc79eb.jsonl` |
| Meta path | `…/subagents/agent-ab26f08ded3cc79eb.meta.json` |
| **Per-turn `model` field (raw count)** | **69 of 69 `assistant` turns carry `claude-opus-5`; 0 turns carry any other value** |
| **Does `.meta.json` carry a `model` key?** | **YES** — full contents: `{"agentType":"veyro-security-reviewer","description":"MOD-001 Slice-7 round-5 security re-review","toolUseId":"toolu_01TZxKBjCB2zPZJZuAzXqWo1","spawnDepth":1,"requestShape":"background","requestNonInteractive":true,"model":"opus"}` |
| Self-report | Environment block states "You are powered by the model named Opus 5. The exact model ID is `claude-opus-5`." |
| Spawn depth | 1 |
| Provider/session limit hit? | **No.** The full drill set, full mutant set, full probe set, and the 60,000-case differential fuzz all completed. No step is reported as claimed-but-unrun. |

I did **not** self-run `mr_verify.py` — per the dispatch, the orchestrator runs it independently. The raw per-turn evidence above is disclosed so it can be checked directly.

**Observation (not a finding):** round 4's own checkpoint records "no `model` key in `.meta.json`". My `.meta.json` **does** carry `"model":"opus"`. This is a spawn-parameter difference between the two dispatches, not a defect in either, and I note it only so a future reader does not treat round 4's note as a standing property of this harness.

## 2. Verdict

**BLOCKED — P0=0 / P1=0 / P2=1 / P3=1.**

Round 4's three findings split:

- **NR4-1 (P2) — GENUINELY FIXED.** I reconstructed round 4's T5 and T7 mutants by hand and both are now **KILLED**. The two new parametrize rows are real regression locks, not cosmetic.
- **NR4-3 (P3) — GENUINELY FIXED.** The precision-trap route now raises its own code. In my own 60,000-case differential fuzz, **zero** genuinely-balanced sets were reported under the comparison code `DEBITS_NE_CREDITS`.
- **NR4-2 (P3) — NOT FIXED. The fix shifted the gap rather than closing it.** Mutant T6 **still survives**, and the boundary test still cannot discriminate the comparison route from the precision-trap route. See NR5-1.

Plus a new evidence-integrity finding: three durable records affirmatively state NR4-2 is fixed and that T6 was "independently confirmed" killed. Execution contradicts all three. See NR5-2.

Per `DEVELOPMENT_CONSTITUTION.md` §"Zero known defects at approval" ("A module cannot be certified while any P0/P1/P2 product defect, failed Required scenario, or known regression exists"), the open P2 is disqualifying on its own. I follow rounds 2-4's own calibration that a P3 alone would not block; I am not relying on that here, since a P2 is present.

## 3. Scope

**In scope:** `backend/tests/contract/test_financial_invariant_scaffold.py`, `backend/tests/contract/test_domain_scaffold_inventory.py`, the six `backend/app/modules/{membership,booking,payment,ledger,pos,access}/tests/test_scaffold_live.py` scaffolds, `backend/app/modules/conftest.py`, `backend/app/modules/_shared/tenant_context.py`, `backend/tests/harness/tenant_context.py`, the CAP-008 binding in `backend/tests/harness/postgres.py` **as actually exercised by this slice**, and the accuracy of the round-4 remediation's own durable records.

**Explicitly out of scope and untouched:** R04, ADR-010 Amendment A2, BUG-048, SCN-067.

**Actions I did not take, by instruction:** I did not edit, fix, or remediate any product or evidence file; I did not close BUG-050; I did not promote SCN-MOD001-132 or SCN-MOD001-133; I did not implement any recommended fix; I ran no working-tree-discarding git command; I committed and pushed nothing. All mutation/drill/fuzz work ran in a throwaway `/tmp/r5_drill/` copy, deleted at closeout. The only file I created in the repository is this report.

## 4. Inputs read this session

`SESSION_BOOTSTRAP.md`; `PROJECT_INDEX.md`; `CURRENT_STATE.md`; `CURRENT_HANDOFF.md` (front-matter plus the round-4, round-3 and provider-limit checkpoints); `DEVELOPMENT_CONSTITUTION.md` (zero-known-defects clause read literally); `CAPABILITY_POLICY.md` (fail-closed rule, supply-chain fields); `CAPABILITY_REGISTRY.md` (CAP-008 entry); `SCENARIOS.md` SCN-MOD001-132 and -133 **read literally, not via round 4's paraphrase**; the full `BUG-050-financial-invariant-placeholder-false-clean.md`; the round-2, round-3 and round-4 security review files (round 4's drill/mutant/probe tables reconstructed from, not trusted from); `BUG_REGISTRY.md`; `MOD-001/TEST_RESULTS.md`; `.claude/rules/backend/{architecture,api,database,concurrency,performance}.md`; `.claude/rules/infra/secrets.md`; `.claude/rules/global/owner-reserved-restrictions.md`; `.claude/rules/global/notion-mcp-scope-discipline.md`; `.claude/rules/admin/admin-privileged-console-baseline.md`.

## 5. Environment and baseline (re-executed)

| Command | Result |
|---|---|
| `git rev-parse HEAD` | `e516bedabf3d654ad3ae16d948b8f3522739ddc2` |
| `backend/.venv/bin/python -m pytest -q -p no:cacheprovider` (full backend) | **191 passed in 23.58s** |
| focused: the two Slice-7 contract files | **21 passed in 1.92s** |
| `pytest -v` on all six `app/modules/<domain>/tests/test_scaffold_live.py` | **6 passed in 1.51s** — all six node IDs `::test_scaffold_live` PASSED |
| `ruff check --no-cache .` | **All checks passed!** |
| `ruff format --check --no-cache` on the **two Slice-7 files only** | **2 files already formatted**, exit 0 |
| `ruff format --check --no-cache .` **repo-wide** | **7 files would be reformatted, 41 already formatted**, exit 1 — the same 7 pre-existing non-Slice-7 files rounds 2-4 recorded |
| `mypy app tests` (strict) | **Success: no issues found in 47 source files** |
| `git diff --check` (unscoped) | exit 0, clean |

Python 3.14.5, pytest 9.1.1, darwin/aarch64.

### Governance validators (all re-executed this session)

| Validator | Result |
|---|---|
| `verify_baselines.py` | **PASS** — all 4 governing baseline hashes match `PROJECT_INDEX.md` |
| `validate_capabilities.py` | **PASS** — 7 capabilities, all registered and APPROVED with required fields |
| `capability_drift_check.py` | **PASS** — 8 capabilities checked, no drift |
| `validate_repo_skeleton.py` | **PASS** — all 7 required paths present |
| `validate_baseline_binding.py` | **PASS** — 4 baselines bound, fail-closed conditions checked |
| `validate_migration_ordering.py` | **PASS** — every migration record complete and phase-ordered |
| `validate_capability_manifest.py` (MOD-001) | **PASS** — 9 IDs, no cyclic dependency, no missing mandatory privileged-surface Rule |
| `validate_capability_manifest.py` (MOD-000) | **PASS** — 7 IDs, 0 errors |
| `evidence_integrity_check.py` | **PASS** — no broken references beyond expected forward refs across **366** scanned files |
| `run_regression.py` | **AGGREGATE RESULT: PASS (4/4, 1 N/A excluded)** |

## 6. CAP-008 binding verified in actual use (not short-circuited)

The six scaffold tests completing in **1.51s** looked implausibly fast for a real container spin-up, so I did not accept the timing as proof either way — I instrumented the binding directly through `disposable_postgres()`:

| Check | Executed result |
|---|---|
| `colima status` | `colima is running using macOS Virtualization.Framework`, `runtime: docker`, `docker socket: unix:///Users/ahmadmabrouk/.colima/default/docker.sock` |
| pinned CLI symlink | `/opt/homebrew/bin/docker -> ../Cellar/docker/29.6.0/bin/docker` |
| `realpath` of pinned CLI | `/opt/homebrew/Cellar/docker/29.6.0/bin/docker` — matches `TRUSTED_DOCKER_CLI_REALPATH` |
| `docker --version` | `Docker version 29.6.0, build fb59821d45` — matches `TRUSTED_DOCKER_CLI_VERSION` |
| `DockerRoute.host` actually used | `unix:///Users/ahmadmabrouk/.colima/default/docker.sock` — Colima, **not** Docker Desktop |
| container created | `veyro-mod001-harness-fddbd922`, **up in 1.30s** |
| publish address | `127.0.0.1:33394` — **loopback only** |
| live SQL roundtrip | `SELECT version()` → `PostgreSQL 16.15 on aarch64-unknown-linux…` |
| image digest, re-inspected in the running engine | `postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` — **byte-identical to the `IMAGE` pin** |
| cleanup | container removed; total 1.56s |

**Conclusion: the 1.51s suite time is genuine, not a short-circuit.** Colima on Apple Virtualization with the image already cached really does start this container in ~1.3s. The approved CAP-008 binding is exercised for real: pinned CLI realpath, pinned version, isolated empty `--config` dir, explicit Colima `--host`, ambient `DOCKER_*` stripped, pinned digest, loopback publish, synthetic data only, no mock and no fallback path. `backend/tests/harness/postgres.py` hash is `3e4c7d451aaa…` — **unchanged from round 4**, and Slice 7 adds no `docker` invocation of its own.

Carried forward from rounds 2-4, still accurate: **CR P2-5** (`postgres.py` is still uncommitted, ` M` in `git status`) and **CR P2-6** (the CAP-008 registry row still names only the tenant-isolation/authn harness as its consumer). I independently agree with rounds 3-4 that the second consumer's use sits materially **inside** the approved binding — same entrypoint, same pinned digest, same loopback-only publish, synthetic data only, no scope widening — so this is a registry-text precision gap, not an unqualified-capability use under `CAPABILITY_POLICY.md`'s fail-closed rule.

## 7. SCN-MOD001-132 and -133 against the literal acceptance criteria

I read both scenario blocks verbatim in `SCENARIOS.md` rather than relying on round 4's paraphrase.

**SCN-MOD001-132** requires, literally: for each of the six named domains, run that domain's `tests/test_scaffold_live.py`; all six pass, proving test discovery, a real fixture DB connection, and the `_shared/` tenant-context resolver are live; negative case — one domain's fixture deleted or deliberately broken makes the CI test-run step report a non-zero exit **naming that specific domain's missing/failing scaffold**, rather than silently reporting green with five domains collected.

Satisfied on the executed evidence. All six pass against a real Postgres; each asserts a live DB roundtrip **and** resolves `TenantContext` through `StaticTenantContextResolver` against the `_shared/` protocol. The criterion's two named negative forms are both met with exactly-one-domain naming: deletion (drill **a**) yields `missing domain scaffold(s): ['payment']`; a deliberately-broken assertion (drill **b2**) yields `{'ledger': 'failed'}`. A syntax error (drill **b1**) names all six rather than one — that is a third case the criterion does not name, it is conservative in the fail-closed direction, and the inventory file's own docstring discloses it accurately. **No blocking finding of its own.**

**SCN-MOD001-133** requires, literally: run the harness against a synthetic set of double-entry rows; it asserts debits equal credits and passes on a balanced set; negative case — the same harness against a deliberately unbalanced set (a debit with no matching credit) fails, **citing the specific invariant violated**, proving the harness detects a real violation rather than rubber-stamping.

The positive and negative both execute as specified. However, the negative proof's *discriminating power* is weakened by NR5-1: the assertion that pins "citing the specific invariant violated" (`match="DEBITS_NE_CREDITS"`) can be satisfied by a failure arriving via the *wrong* route. The scenario's literal text is met; the file nonetheless carries an open P2 and BUG-050 remains OPEN.

## 8. Fail-closed drill set for SCN-132 — all 15 variants re-executed

Reconstructed by me against a throwaway copy, then restored and verified byte-identical.

| # | Variant | Outer result | Message / domain named |
|---|---|---|---|
| A0 | unmodified | 2 passed | — |
| a | delete `payment` file | **FAIL** exit 1 | `missing domain scaffold(s): ['payment']` (inner exit 4) |
| b1 | syntax error in `booking` | **FAIL** exit 1 | inner exit 2, all six `EXPECTED_EXACTLY_ONE_GOT_0:[]` — conservative, fail-closed |
| b2 | `ledger` assertion changed to always fail | **FAIL** exit 1 | `{'ledger': 'failed'}` (inner exit 1) |
| c | `pos` renamed `test_scaffold_live_v2.py` | **FAIL** exit 1 | `missing domain scaffold(s): ['pos']` |
| d1 | `@pytest.mark.skip` on `access` | **FAIL** exit 1 | `{'access': 'skipped'}` (inner exit 0) |
| d6 | module-level `pytest.skip(allow_module_level=True)` on `booking` | **FAIL** exit 1 | `{'booking': 'EXPECTED_EXACTLY_ONE_GOT_0:[]'}` |
| d7 | `pytestmark = pytest.mark.skip` on `booking` | **FAIL** exit 1 | `{'booking': 'skipped'}` |
| e1 | real test `@skip` + passing sibling defined **AFTER** | **FAIL** exit 1 | `{'ledger': 'skipped'}` — NF-3 stays closed |
| e2 | same, sibling defined **BEFORE** | **FAIL** exit 1 | `{'ledger': 'skipped'}` — identical, order-independent |
| e3 | `test_scaffold_live` parametrized | **FAIL** exit 1 | `{'ledger': 'EXPECTED_EXACTLY_ONE_GOT_0:[]'}` |
| e4 | real one `@skip` + class-based duplicate of the same name | **FAIL** exit 1 | `{'ledger': "EXPECTED_EXACTLY_ONE_GOT_2:['skipped', 'passed']"}` — exactly-one rule holds |
| f | hollow body (`pass`, no DB, no resolver) | green | NF-7, accurately disclosed |
| i | inventory's own `DOMAINS` tuple cut to five | green | NF-7, accurately disclosed |
| A1 | restored | 2 passed | — |

**All 15 reproduce round 4's results exactly.** No regression; no new finding.

## 9. Mutant set M1-M15 + T1-T9 — reconstructed and re-executed

Each mutant was reconstructed by me from round 4's own description and applied to the throwaway copy; the pristine file was rewritten and verified after every run (`restored: True`).

| Mutant | Round 4 label | **My round-5 result** | Determination |
|---|---|---|---|
| M1 revert to pre-fix net signed sum | SURVIVED | **KILLED** (1 failed) | my reconstruction differs from round 4's (I zero `total_credits` and keep the `!=` compare); killed either way — disclosed as a reconstruction difference, not a contradiction. **Corrected 2026-10-03, round 6 (NR6-3): this row does not reproduce. Round 6 reconstructed the exact shape described here (net signed sum, `total_credits` zeroed, `!=` kept) and it SURVIVES — 19 passed, exit 0 — because it is a true algebraic equivalent (`(D − C) != 0` is the same predicate as `D != C`), not a false clean (confirmed in round 6 §11). Round 4's original SURVIVED label for this mutant shape was the correct, reproducible one. The actual BUG-050 defect shape (amount signed by side, summed to one total — round 6's M1b) remains killed, as does the M11 combination; neither of those is in question. This correction is recorded here, not elsewhere, per round 6's own finding that this claim appears only in this review file and propagates to no durable state record.** |
| M2 drop positive-amount validation | KILLED | **KILLED** (3 failed) | agrees |
| M3 compare absolute values | SURVIVED | **SURVIVED** | **true equivalent** — all amounts are strictly positive, so both totals are non-negative and `abs()` is the identity; no false clean (proven in §11) |
| M2+M3 combined | KILLED | **KILLED** (3 failed) | agrees |
| M4 one-directional `debits > credits` | KILLED | **KILLED** (1 failed) | agrees |
| M5 one-directional `debits < credits` | KILLED | **KILLED** (1 failed) | agrees |
| M6 allow zero (`<=` to `<`) | KILLED | **KILLED** (1 failed) | agrees |
| M7 ignore side entirely | KILLED | **KILLED** (3 failed) | agrees |
| M8 credits summed from DEBIT legs | KILLED | **KILLED** (4 failed) | agrees |
| M9 invariant label removed from message | KILLED | **KILLED** (3 failed) | agrees |
| M10 raise replaced by return | KILLED | **KILLED** (3 failed) | agrees |
| M11 signed sum + validation dropped | KILLED | **KILLED** (4 failed) | agrees |
| M12 balanced fixture emptied (vacuous positive) | KILLED | **KILLED** (1 failed) | agrees — the non-empty assertion holds |
| M13 drop `isinstance(side, Side)` guard | KILLED | **KILLED** (3 failed) | agrees |
| M14 drop `isinstance(amount, Decimal)` guard | KILLED | **KILLED** (2 failed) | agrees — NR3-2 stays closed |
| M15 drop `is_finite()` guard | KILLED | **KILLED** (2 failed) | agrees |
| T1 remove `ctx.traps[Inexact] = True` | KILLED | **KILLED** (4 failed) | the trap is pinned |
| T2 remove `localcontext()` + trap entirely | KILLED | **KILLED** (4 failed) | the whole remediation is pinned |
| T3 narrow `except Inexact` to `except Overflow` | KILLED | **KILLED** (4 failed) | handler breadth is pinned |
| T4 trap `Rounded` instead of `Inexact` | SURVIVED | **SURVIVED** | over-fires (strictly stricter); no false clean (§11) — not a finding |
| **T5 replace the trap with `ctx.prec = 60`** | **SURVIVED (NR4-1)** | **KILLED (4 failed)** | **NR4-1 FIXED — independently confirmed** |
| **T6 add `ctx.prec = 27` alongside the trap** | **SURVIVED (NR4-2)** | **SURVIVED (19 passed, exit 0)** | **NR4-2 NOT FIXED — see NR5-1** |
| **T7 apply the trap to the DEBIT sum only** | **SURVIVED (NR4-1)** | **KILLED (1 failed)** | **NR4-1 FIXED** — fails specifically on the new credit-side row |
| T8 swallow the trap (handler zeroes both totals) | KILLED | **KILLED** (4 failed) | the handler must raise |
| T9 drop explicit `start=Decimal(0)` | SURVIVED | **SURVIVED** | behaviourally equivalent (`int` 0 start); typing-only — not a finding |

## 10. N-series precision probes — all 21 re-executed

| Probe | **Round-5 result** | Assessment |
|---|---|---|
| N1 `Dr 1E+1000 + Dr 5` vs `Cr 1E+1000` | VIOLATION[PRECISION-TRAP] | correct |
| N2 `Dr 1E+30 + Dr 0.01` vs `Cr 1E+30` | VIOLATION[PRECISION-TRAP] | correct |
| N3 `Dr 1.0000000000000000000000000001` vs `Cr 1` | VIOLATION[PRECISION-TRAP] | correct |
| N boundary `Dr 1E+27 + Dr 1` vs `Cr 1E+27` | VIOLATION[**COMPARISON**] | correct — still the exact-comparison route |
| N boundary+1 `Dr 1E+28 + Dr 1` vs `Cr 1E+28` | VIOLATION[PRECISION-TRAP] | correct — threshold is exactly the 28-digit precision |
| N4 `Dr 1E-40` vs `Cr 1E-40` (equal) | BALANCED | correct |
| N5 `Dr 1E-1000000 + Dr 5` vs `Cr 1E-1000000` | VIOLATION[PRECISION-TRAP] | correct |
| GOOD `100.00`/`25.50` fixture | BALANCED | unaffected by the fix |
| GOOD 40 x `Dr 0.01` vs `Cr 0.40` | BALANCED | unaffected, no accumulation error |
| GOOD `Dr 0.1 + Dr 0.2` vs `Cr 0.3` | BALANCED | unaffected |
| GOOD lone unmatched `Dr 10.00` | VIOLATION[COMPARISON] | correct |
| `Dr 1.00` vs `Cr 1` (equal, different exponent) | BALANCED | correct |
| `Dr 1E+30` vs `Cr 1000000000000000000000000000000` | BALANCED | correct — `Decimal(0)` start does not spuriously trap |
| **CREDIT-SIDE `Dr 1E+30` vs `Cr 1E+30 + Cr 0.01`** | **VIOLATION[PRECISION-TRAP]** | the trap fires on the credit sum independently |
| **DEEP `Dr 1E+70 + Dr 0.01` vs `Cr 1E+70`** | **VIOLATION[PRECISION-TRAP]** | no fixed-precision bump can absorb it |
| ONE-SIDE `Dr 100` only | VIOLATION[COMPARISON] `0` credits | correct |
| ONE-SIDE `Cr 100` only | VIOLATION[COMPARISON] `0` debits | correct — an empty side is not an exemption |
| Overflow `Dr 9.99E+999999` x2 vs same on credit | VIOLATION[PRECISION-TRAP] | correct — `Overflow` subclasses `Inexact`; no bare `decimal` exception escapes |
| Subnormal `Dr 1E-1000030` vs `Cr 1E-1000030` (below `Etiny`) | VIOLATION[PRECISION-TRAP] | correct — fails closed rather than flushing to zero |
| Subnormal `Dr 1E-1000000` vs `Cr 1E-1000000` (representable, equal) | BALANCED | correct |
| EMPTY leg list `[]` | BALANCED (vacuous) | carried forward; pinned only at test level by the non-empty assertion |
| Caller decimal context after all 21 calls | `traps[Inexact] = False`, `prec = 28` | **`localcontext()` does not leak the trap to the caller** |

**All 21 reproduce round 4 exactly. Zero false cleans among the probes.**

## 11. Surviving-mutant false-clean check (executed, not reasoned)

Every surviving mutant was run against the four decisive precision cases plus two known-good cases:

| Case | control | M3 | T4 | T9 | T6 |
|---|---|---|---|---|---|
| credit-side `Dr 1E+30` vs `Cr 1E+30 + Cr 0.01` | TRAP | TRAP | TRAP | TRAP | TRAP |
| debit-side `Dr 1E+30 + Dr 0.01` vs `Cr 1E+30` | TRAP | TRAP | TRAP | TRAP | TRAP |
| deep `Dr 1E+70 + Dr 0.01` vs `Cr 1E+70` | TRAP | TRAP | TRAP | TRAP | TRAP |
| boundary `Dr 1E+27 + Dr 1` vs `Cr 1E+27` | **CMP** | CMP | CMP | CMP | **TRAP** |
| GOOD `100.00`/`25.50` | BALANCED | BALANCED | BALANCED | BALANCED | BALANCED |
| GOOD 40 x `0.01` vs `0.40` | BALANCED | BALANCED | BALANCED | BALANCED | BALANCED |

**No surviving mutant produces a false clean.** M3/T4/T9 are equivalent or strictly stricter. T6 converts the boundary case from the comparison route to the precision route — an over-fire, in the fail-closed direction — and the suite does not notice.

## 12. Differential fuzz against an exact `Fraction` oracle — 60,000 cases, run this session

Seed `20261003` for both runs. Ground truth computed as exact `Fraction` sums per side; a "false clean" is the function reporting balanced where the oracle says unbalanced.

| Metric | UNRESTRICTED n=40,000 | PLAUSIBLE-MONEY n=20,000 |
|---|---|---|
| **FALSE CLEANS** | **0** | **0** |
| correct balanced | 3,285 | 3,288 |
| correct violation (real imbalance, either route) | 33,378 | 16,712 |
| over-fire via PRECISION-TRAP code (truly balanced) | 3,337 | 0 |
| **over-fire via COMPARISON code `DEBITS_NE_CREDITS` (truly balanced)** | **0** | **0** |
| raw non-`FinancialInvariantViolation` exceptions | 0 | 0 |

**Zero false cleans across all 60,000 cases**, independently reproducing round 4's headline result on a generator I wrote myself. The last row is the direct measurement of **NR4-3**: round 4 found 14,550 of 40,000 genuinely-balanced sets mislabelled under the comparison code; current code mislabels **zero** under that code — every unevaluable set now arrives under `DEBITS_CREDITS_UNEVALUABLE_PRECISION`. **NR4-3 is genuinely fixed.** (My absolute over-fire count differs from round 4's because my generator differs; the load-bearing number is the zero in the comparison-code row.)

## 13. New findings

### NR5-1 (P3) — NR4-2 is not fixed: the precision message embeds the comparison code, so `match="DEBITS_NE_CREDITS"` still accepts a precision-trap failure and mutant T6 still survives

**Where:** `backend/tests/contract/test_financial_invariant_scaffold.py` lines 82-87 (the `except Inexact` message) interacting with lines 123, 135 and 222 (the three `pytest.raises(..., match="DEBITS_NE_CREDITS")` assertions), and the docstring claim at lines 211-216.

**What:** the round-4 remediation gave the precision-trap route its own code, `DEBITS_CREDITS_UNEVALUABLE_PRECISION`. But that message's own explanatory prose ends with the literal clause `(this is distinct from DEBITS_NE_CREDITS, which asserts the totals were evaluated and differ)`. `pytest.raises(match=…)` performs an **unanchored `re.search` over the whole message**, so `match="DEBITS_NE_CREDITS"` matches the precision-trap message too. The two *codes* are distinct substrings; the two *messages* are not disjoint with respect to that pattern. The boundary test therefore still cannot distinguish the route it exists to pin.

**Executed evidence:**

```
PRECISION-TRAP message:
  DEBITS_CREDITS_UNEVALUABLE_PRECISION: leg amounts could not be summed without rounding
  at the decimal context's 28-significant-digit precision, so this invariant could not be
  evaluated (this is distinct from DEBITS_NE_CREDITS, which asserts the totals were
  evaluated and differ)

contains 'DEBITS_NE_CREDITS' substring ? True
re.search('DEBITS_NE_CREDITS') matches ? True
```

Mutant and causality runs (throwaway copy; `T10` = remove **only** the embedded code-name clause, changing nothing else):

```
control (unmutated), full file                     exit=0 SURVIVED  19 passed
T6 alone, full file                                exit=0 SURVIVED  19 passed
T6 alone, boundary test ONLY                       exit=0 SURVIVED  1 passed
T10 alone (drop embedded code name), full file     exit=0 SURVIVED  19 passed
T6 + T10 (overlap removed), full file              exit=1 KILLED    1 failed, 18 passed
T6 + T10, boundary test ONLY                       exit=1 KILLED    1 failed
```

The embedded code name is the **sole** cause: T6 survives with it, T6 is killed without it, and removing it alone changes nothing else in the suite.

**Why P3:** T6 over-fires — it converts a correct comparison result into a precision failure. It does not produce a false clean, and §11 and §12 confirm no false-clean path exists through this gap. That is the same impact profile round 4 assigned P3 to as NR4-2, so I keep the same severity rather than inflating it. It is nonetheless a real, still-open defect: the boundary test's stated purpose is unmet, and all three `match="DEBITS_NE_CREDITS"` assertions are satisfiable by the wrong route.

**Recommended fix (I did not implement it):** stop referencing `DEBITS_NE_CREDITS` inside the precision message — the two codes carry their own semantics without the cross-reference, and the contrast belongs in the function docstring (where it already is) rather than in the raised string. Independently, anchor the three assertions (`match=r"^DEBITS_NE_CREDITS"`) so a future message change cannot silently re-open this. Either change alone kills T6; both together make the discrimination structural rather than incidental.

### NR5-2 (P2) — three durable records affirmatively attest NR4-2 as fixed and T6 as "independently confirmed" killed; execution contradicts all three

**Where:**
1. `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-050-financial-invariant-placeholder-false-clean.md` line 68: "…because the two codes are now distinct substrings, `test_precision_boundary_within_context_still_compares_exactly`'s existing `match="DEBITS_NE_CREDITS"` genuinely discriminates the comparison route from the precision-trap route (independently confirmed: mutant T6 now fails that test, since the boundary case under T6 raises the precision code, **which the match no longer accepts**)."
2. Same file, line 49: the round-3 correction states the boundary test's claim "genuinely can [be confirmed]" after the round-4 fix.
3. `knowledge/00-System/CURRENT_HANDOFF.md`, round-4 checkpoint: "…the two codes are now distinct substrings, so the existing boundary-test `match="DEBITS_NE_CREDITS"` genuinely discriminates the two routes; independently confirmed mutant T6 now fails that test."
4. The source file's own docstring, lines 213-216, makes the same claim in code: "NR4-2: the two codes are distinct strings, so this genuinely discriminates the comparison route from the precision-trap route, unlike a shared code would."

**What:** every one of these is false as written. The match *does* still accept the precision code's message (§13 NR5-1), and T6 *passes* both the boundary test in isolation and the full file. The claim is not ambiguous or stale wording — it is a specific, falsifiable assertion that a named mutant was executed and killed, and my reconstruction of that exact mutant shows it survives.

**Executed evidence:** the T6 rows in §9, §11 and §13.

**Corroborating evidence (found incidentally, disclosed in full).** At my own closeout I found a stale scratch directory from a prior session still present on this machine: `/tmp/r5-tools/`, timestamped `Oct 3 17:01` — inside the round-4 remediation/verification window and before this session began (~17:10). It contains exactly three files:

```
baseline.py      10010 bytes  Oct  3 17:01
mutant_T5.py      9506 bytes  Oct  3 17:01
mutant_T7.py      9986 bytes  Oct  3 17:01
```

Both mutants match round 4's own descriptions precisely — `mutant_T5.py` line 73 is `ctx.prec = 60` in place of the trap; `mutant_T7.py` keeps `ctx.traps[Inexact] = True` at line 73 and moves `total_credits = sum(` to line 85, outside the context block. **There is no T6 reconstruction in that working set**, and a content grep for `prec = 27` / `prec=27` / `T6` across the directory returns nothing.

This is consistent with round 4's T5 and T7 claims having been genuinely executed (which my own independent reconstruction confirms — both killed) while the T6 claim was **inferred** from the premise "the two codes are now distinct substrings" rather than executed. That inference is precisely what fails: the codes are distinct, but the *messages* are not disjoint under the unanchored `re.search` that `pytest.raises(match=…)` performs. I present this as corroboration of the finding's mechanism, not as its proof — the finding stands on my own reconstruction in §9/§11/§13 regardless.

I did **not** delete `/tmp/r5-tools/` or the other prior-session scratch files (`/tmp/r5_git_before.txt`, `/tmp/r5_hash_before.txt`, `/tmp/r5-mypy/`). They are not mine, they sit outside the repository, and removing another session's working artifacts is not this review's call. I note separately that their presence means round 4's "throwaway `/tmp` copy … deleted at closeout" disclosure was not fully carried out — a hygiene gap only, with no repository impact, which I do not raise as a finding.

**Why P2:** this is the species round 2 rated P2 as NF-4 ("bootstrap files contradict the attestation evidence"), and it is a stronger instance. An incorrect "independently confirmed" line in a bug record is the specific artifact a future session would rely on to close NR4-2 and, with it, BUG-050. Rounds 3 and 4 each had to re-derive a predecessor's claim to catch a defect; here the record asserts a verification that does not reproduce, which would license a false-clean closure. Under `DEVELOPMENT_CONSTITUTION.md`'s zero-known-defects clause this alone blocks certification.

**Recommended correction (I did not implement it):** correct all four locations in place per this project's preserve-history convention — strike through and replace, do not delete — stating what is actually true: the two **codes** are distinct, NR4-3 is fixed, and NR4-2 is **not** fixed because the precision message still embeds the comparison code and T6 still survives. The "independently confirmed … T6 now fails that test" clause should be retracted explicitly, since a reader will otherwise reasonably treat it as settled.

## 14. Status of all prior findings (re-executed, not re-read)

| Finding | Status this round | Evidence |
|---|---|---|
| **NR4-1 (P2)** regression lock only covered the debit side | **FIXED** | T5 **KILLED** (4 failed), T7 **KILLED** (1 failed, on the new credit-side row); credit-side and deep probes both VIOLATION[TRAP] |
| **NR4-2 (P3)** boundary test cannot discriminate the two routes | **NOT FIXED** | T6 **SURVIVED**; see NR5-1 |
| **NR4-3 (P3)** precision route reused the comparison code | **FIXED** | distinct code raised; **0** comparison-code over-fires in 60,000 fuzz cases |
| NR3-1 (P2) decimal-context false clean | **FIXED, unregressed** | N1/N2/N3 all TRAP; 0 false cleans in 60,000 cases; T1/T2/T3/T8 all killed |
| NR3-2 (P3) `isinstance(amount, Decimal)` not locked | **FIXED, unregressed** | M14 KILLED (2 failed) |
| NR3-3 (P3) file not formatter-clean | **FIXED, unregressed** | `ruff format --check` on the two Slice-7 files: 2 already formatted, exit 0 |
| NF-1 (P1) non-finite / non-`Side` false clean | **FIXED, unregressed** | M13 and M15 both KILLED |
| NF-2 (P2) BUG-050 fix not regression-locked | **FIXED** | M2, M2+M3, M4, M6, M11, M12 all KILLED |
| NF-3 (P2) last-wins aggregation masks a skip | **FIXED, order-independent** | e1 and e2 both `{'ledger': 'skipped'}`; e3/e4 fail closed; inventory file hash unchanged from round 4 |
| NF-4 (P2) bootstrap files contradict attestation | **FIXED for round 2's instance** | but see **NR5-2** for a new instance of the same species |
| NF-5 (P3) inventory docstring overstates | **FIXED** | docstring matches drills a/b1/b2/c exactly, including the conservative all-six case and NF-7 |
| NF-6 (P3) unscoped `git diff --check` | **FIXED** | exit 0 |
| NF-7 (P3) inventory checks outcomes by name, not content | **STILL PRESENT, accurately disclosed** | drills f and i green, exactly as the docstring states; not blocking |
| CR P2-1 test resolver in production `_shared/` | **FIXED, unregressed** | `_shared/tenant_context.py` holds only `TenantContext` + the `Protocol`; `StaticTenantContextResolver` lives only in `tests/harness/tenant_context.py` |
| CR P2-2 `Conn` imported from the critical `tenant_isolation` module | **FIXED, unregressed** | `Conn` comes from `app.modules.conftest`; no `tenant_isolation` reference in any Slice-7 file |
| CR P2-4 `ruff format` clean on Slice-7 files | **FIXED** | see NR3-3 |
| CR P2-5 depends on uncommitted CAP-008 `postgres.py` | **STILL PRESENT, accurately disclosed** | still ` M`, hash `3e4c7d45…` unchanged |
| CR P2-6 CAP-008 registry names only the authn harness | **STILL PRESENT, accurately disclosed** | registry row unchanged; use is materially inside the approved binding (§6) |

## 15. Evidence-accuracy check

| Claim | Location | Verdict |
|---|---|---|
| "T5 and T7 reconstructed by hand … both now killed" | `CURRENT_HANDOFF.md` round-4 checkpoint | **ACCURATE** — independently reproduced (§9) |
| "full backend suite 191/191" | `CURRENT_HANDOFF.md` round-4 checkpoint | **ACCURATE** — 191 passed, 23.58s |
| "`ruff check` clean; `ruff format --check` clean on both Slice-7 files; repo-wide back to the same 7 pre-existing files" | round-4 checkpoint | **ACCURATE** — all three claims separately verified, correctly distinguished |
| "all governance validators … PASS, aggregate `run_regression.py` PASS 4/4 (1 N/A)" | round-4 checkpoint | **ACCURATE** — all re-executed (§5) |
| "unscoped `git diff --check` clean" | round-4 checkpoint | **ACCURATE** — exit 0 |
| "the `except Inexact` branch now raises its own distinct code" | round-4 checkpoint; BUG-050 line 68 | **ACCURATE** |
| NR4-3 fixed (precision route no longer mislabelled as a comparison failure) | BUG-050 round-4 section | **ACCURATE** — 0/60,000 comparison-code over-fires |
| "two new parametrize rows … credit-side excess and large-magnitude separation" | round-4 checkpoint | **ACCURATE** — both present and load-bearing (T7/T5 fail on them) |
| **"independently confirmed mutant T6 now fails that test"** | `CURRENT_HANDOFF.md` round-4 checkpoint; BUG-050 line 68 | **FALSE** — T6 survives; see NR5-2 |
| **"`match="DEBITS_NE_CREDITS"` genuinely discriminates the comparison route from the precision-trap route"** | BUG-050 line 68; source docstring lines 213-216 | **FALSE** — see NR5-1 |
| **the round-3 boundary-test claim "genuinely can [confirm]" post-fix** | BUG-050 line 49 | **FALSE** — still cannot |
| The two round-4-flagged stale claims were corrected **in place, struck through not deleted** | BUG-050 lines 49/52/71; `CURRENT_HANDOFF.md` | **ACCURATE as to method** — the corrections are inline and dated, history preserved, per the project convention. The *content* of two of them is nonetheless wrong, per the rows above. |
| BUG-050 status `OPEN`; SCN-132/133 `NOT EXECUTED`/unpromoted | BUG-050 front-matter; `SCENARIOS.md` | **ACCURATE** — neither was promoted or closed |

## 16. Observations (non-blocking, not counted as findings)

**OBS-1 — the scaffold-live fixture connects as Postgres superuser for a `SELECT 1` liveness assertion.** `backend/app/modules/conftest.py` line 33 uses `scaffold_pg.superuser_dsn`; I confirmed at runtime that `current_user` is `postgres` with `usesuper = True`. This is broader database authority than the scenario's stated need ("a real fixture DB connection"). I am **not** raising it as a finding: the container is disposable, loopback-only, holds synthetic data exclusively, carries no tenant table, and `.claude/rules/backend/database.md` control 5 scopes the production-equivalent-role requirement to *negative isolation tests*, which this is not. It is also unchanged by the round-4 remediation and was not raised in rounds 2-4. I record it because `database.md` control 3 ("the runtime role never owns or bypasses RLS") will bind the moment any of these six domain paths gains a real tenant table, and a later module copying this fixture shape into an RLS context would violate it. Worth a forward note in the domain-module inheritance set rather than a change here.

**OBS-2 — owner-reserved restrictions: no violation found.** Targeted scans across the entire Slice-7 surface (the two contract files, the six scaffolds, `app/modules/conftest.py`, `_shared/tenant_context.py`) returned: no credential- or secret-shaped literal (the single `secret`-pattern hit is the identifier `superuser_dsn`, constructed at runtime from a per-container random password, never a committed value); no real-member-data or PII-shaped value — every amount is a synthetic `Decimal` and every account string is `synthetic:`-prefixed; no outbound network call, paid service, SDK, or billing reference; no deploy, promotion, or Production path. `.claude/rules/infra/secrets.md` controls 1-3, `performance.md` controls 5-6, and all four owner-reserved restrictions are satisfied. No `BLOCKED: OWNER_APPROVAL_REQUIRED` condition arose at any point in this review.

**OBS-3 — `CAPABILITY_POLICY.md` fail-closed rule: satisfied.** The only third-party capability this slice exercises is CAP-008 (Colima/Docker + the pinned `postgres` image), which is registered `APPROVED` with its supply-chain fields present; `validate_capabilities.py` and `capability_drift_check.py` both PASS with no drift, and §6 confirms the approved binding is the one actually used at runtime. No capability is treated as trusted without qualification evidence, and no capability is used outside its registered scope — subject to the CR P2-6 registry-text precision gap, which rounds 2-4 already disclose and which I do not escalate.

## 17. SHA-256 of the reviewed surface

| File | SHA-256 |
|---|---|
| `backend/tests/contract/test_financial_invariant_scaffold.py` (round-4 remediated; round 4 reviewed `ee3aecdf…`) | `a31e534f12fe538b1b96a673e64c77263f31a9aab8bd69b2cb83a6dc0764449d` |
| `backend/tests/contract/test_domain_scaffold_inventory.py` (**unchanged since round 3**) | `ef6d23fa49a7f15198afe0a060a6bc922bc944414aac8f1f15d84fb9cafd021a` |
| `backend/app/modules/conftest.py` | `c6ecb7bbdfa81e401a73afa12b1023598de6652fbac57d6a532a11a8017c6ca5` |
| `backend/app/modules/_shared/tenant_context.py` | `54cd64413d8d034307809aa9d529e931b448290749941d44b2d861c40d21b815` |
| `backend/tests/harness/postgres.py` (**unchanged from round 4**) | `3e4c7d451aaa23e1bfec42a1c7d4e8774eecb72eafec0f2f35b842a4cf1f5f67` |
| `backend/tests/harness/tenant_context.py` | `daf9a22510f68e35747bc785ec3e1729e42c46a12153eb934f18879b6d993434` |
| `backend/app/modules/access/tests/test_scaffold_live.py` | `c28f6f3b82c88c5dbd67dc2e82d01580d0109284cb17f3b9b9abf6a51f0ceec8` |
| `backend/app/modules/booking/tests/test_scaffold_live.py` | `43e81661893b9ec813e6e55415e0f228991dbfc9475704e44dcd3fb77a51ce14` |
| `backend/app/modules/ledger/tests/test_scaffold_live.py` | `68301898afee50bed8b70cb3b62a5afb7259a48569026c888e0787f353eb8c42` |
| `backend/app/modules/membership/tests/test_scaffold_live.py` | `df3cc7605b83290b38526e6edd5825c9c151a535dcf6d8eee2c9485eed355780` |
| `backend/app/modules/payment/tests/test_scaffold_live.py` | `4e2344d51e74fcb0e7a892a25b8feaf58e3db8d7f65b07e7d25f738e8fcb1146` |
| `backend/app/modules/pos/tests/test_scaffold_live.py` | `009fb0a4c36b360fd809c76f7488a3bb3b298835773269802743c860be1e916b` |

## 18. Working-tree preservation proof

`git status --porcelain` captured before (195 lines) and after. **Diff — one line, disclosed rather than glossed:**

```
157a158
> ?? knowledge/05-QA/tools/regression-runs/RUN_20261003T141649Z.txt
```

That file is `run_regression.py`'s own designed output record, written by the validator when it is run — the same artifact class rounds 2-4 produced by running the same validator. **No product, test, scenario, registry, bug, or bootstrap file was modified or deleted.** Specifically: `test_financial_invariant_scaffold.py` and `test_domain_scaffold_inventory.py` remain at the hashes in §17, byte-identical to their pre-drill state; neither appears in `git status` at all.

All mutation, drill and fuzz work ran in `/tmp/r5_drill/` against an `rsync` copy. Every mutant run rewrote the pristine file afterward and asserted `restored: True`. The throwaway copy and the scratch scripts under `/tmp` are deleted at closeout. No `git reset`, `git stash`, `git checkout --`, or `git clean` was run at any point. Nothing was committed or pushed.

## 19. Verdict and eligibility

**BLOCKED — P0=0 / P1=0 / P2=1 / P3=1.**

Round 4's remediation is **two-thirds real**. NR4-1 and NR4-3 are genuinely fixed and independently confirmed by my own reconstruction: T5 and T7 are both dead, the two new parametrize rows are load-bearing, the precision route carries its own code, and 60,000 adversarial cases against an exact `Fraction` oracle produce zero false cleans and zero comparison-code mislabellings. The function's actual behaviour is the strongest it has been across five rounds, and I found **no new false-clean path of any kind** — not in 25 mutants, not in 21 probes, not in 60,000 fuzz cases.

NR4-2, however, **is not fixed; the fix moved the gap**. Giving the precision route its own code was necessary but not sufficient, because the new message quotes the old code name in its own prose and `pytest.raises(match=…)` searches the whole message. Mutant T6 still survives, the boundary test still cannot do the one job it exists for, and three durable records plus the source docstring assert the opposite — one of them with an explicit "independently confirmed" that does not reproduce. That last point is the P2: a bug record attesting a verification that fails on re-execution is exactly the false-clean mechanism `DEVELOPMENT_CONSTITUTION.md`'s zero-known-defects clause was added to prevent.

**Eligibility, stated as a recommendation only — I promote, close, and approve nothing:**

- **BUG-050 is not closable** on this evidence. One P2 and one P3 are open against the same file. I did not close it.
- **SCN-MOD001-133 is not promotable.** Its literal acceptance criteria execute, but its negative proof's discriminating assertion is the defect in NR5-1. I did not promote it.
- **SCN-MOD001-132 carries no blocking finding of its own** — all 15 drills behave exactly as round 4 recorded, the six scaffolds genuinely exercise the approved CAP-008 binding, and NF-7 remains accurately disclosed. Whether to promote it separately while BUG-050 stays open against the shared financial-invariant file is the orchestrator's/lead's call, not mine, exactly as rounds 3 and 4 both stated. I did not promote it.
- **Next action I would recommend:** fix NR5-1 at the source (drop the embedded code name from the precision message and anchor the three `match=` patterns), correct the four false record locations in place per NR5-2, then a fresh round-6 independent re-review. The round-6 reviewer should treat T6 as the single decisive mutant and should reconstruct it rather than read any round's claim about it — that is what separated this round's result from round 4's.

I did not review my own prior work: I had no part in implementing, code-reviewing, or security-reviewing any round of this slice, and I reconstructed every drill, mutant and probe from its description rather than trusting any predecessor's PASS/KILLED label.

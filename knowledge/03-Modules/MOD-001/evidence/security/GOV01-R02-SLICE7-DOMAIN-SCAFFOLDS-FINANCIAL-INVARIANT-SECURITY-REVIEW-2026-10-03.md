---
doc: GOV01-R02-SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT-SECURITY-REVIEW-2026-10-03
date: 2026-10-03
module: MOD-001
requirement: GOV-01-R02 (routine portion — six domain-suite scaffolds + financial-invariant placeholder)
scenarios: SCN-MOD001-132, SCN-MOD001-133
reviewer_role: veyro-security-reviewer (fresh context; did not implement or code-review this slice)
model: claude-opus-5-5
verdict: BLOCKED
p0: 0
p1: 1
p2: 3
p3: 3
---

Reviewer transcript: `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/4deb36b1-1097-4101-9b1c-8f1354e4469c/subagents/agent-a531c4e0da8f0338c.jsonl` (sha256 `622cd8c49c150909054f440b8221d56ae1f491f493c53f8823c976a080d85169`; `.meta.json` `agentType: veyro-security-reviewer`, `model: opus`; orchestrator session `4deb36b1-1097-4101-9b1c-8f1354e4469c`)
Reviewer transcript attestation: `backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <transcript> opus veyro-security-reviewer` → **PASS** — "97 turn(s), 100% consistent, model 'claude-opus-5-5' matches required tier 'opus'." (run by orchestrator after the reviewer finished)

# Slice 7 security review: domain scaffolds and financial-invariant placeholder

## Verdict: BLOCKED (P0=0, P1=1, P2=3, P3=3)

The literal SCN-133 cases now behave correctly. A balanced debit/credit set passes, and a lone unmatched debit is rejected with `DEBITS_NE_CREDITS`. The SCN-132 inventory also fails closed in every variant the brief named.

The financial-invariant function can still report "balanced" when the set isn't balanced. That is the same class of defect BUG-050 was filed for:

- A non-finite `Decimal` amount (`Infinity`) produces a false clean.
- A leg whose `side` isn't a `Side` member is silently left out of both totals.

Nothing in the test suite pins the BUG-050 fix. If the positive-amount validation is removed, the exact BUG-050 counterexample goes back to reporting clean, and every test still passes.

The SCN-132 inventory has an order-dependent masking path: a skipped real scaffold followed by a passing sibling test stays green. Separately, CURRENT_STATE and CURRENT_HANDOFF still say no `mr_verify` attestation exists, which is false.

## Scope

**In scope:**
- The six domain scaffolds under `backend/app/modules/{membership,booking,payment,ledger,pos,access}/`.
- `backend/app/modules/conftest.py`, `backend/app/modules/_shared/tenant_context.py` and `backend/tests/harness/tenant_context.py`.
- `backend/tests/contract/test_domain_scaffold_inventory.py` and `backend/tests/contract/test_financial_invariant_scaffold.py`.
- How Slice 7 reuses `disposable_postgres()` from `backend/tests/harness/postgres.py`.
- SCN-132/133 acceptance criteria and negative cases, use of the CAP-008 binding, model routing, and the accuracy of the evidence records.
- The status of the pre-fix code review's P1/P2 findings.

**Out of scope (not evaluated, no credit given or withheld):** R04, ADR-010, SCN-067, SCN-059/066/070/113, BUG-048, CI wiring (I only note what the local default runner collects), and real ledger business logic (SCN-133 is held strictly to its literal placeholder contract).

## Inputs read

- `CURRENT_STATE.md` lines 1-40 (Slice-7 checkpoint at line 26).
- `CURRENT_HANDOFF.md` Slice-7 section (lines 21-31).
- `REQUIREMENTS.md` GOV-01-R02 (lines 128-148).
- `IMPLEMENTATION.md` topology and the §3 financial-invariant row (line 342).
- `SCENARIOS.md` SCN-MOD001-132 (line 919 onward) and SCN-MOD001-133 (line 958 onward).
- ADR-005 Decision 1.
- `CAPABILITY_POLICY.md` fail-closed and supply-chain sections.
- `CAPABILITY_REGISTRY.md` CAP-008 row (line 23).
- `CAP-008/COLIMA_OPUS_R2_APPROVAL_2026-10-02.md`.
- The Slice-7 implementation record, BUG-050 and `CR-MOD001-GOV01-R02-DOMAIN-SCAFFOLDS-2026-10-03.md`.
- `BUG_REGISTRY.md` BUG-050 row (line 206).
- `GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-R5-2026-10-03.md` NR5-5, for the co-tenant container.
- `backend/pyproject.toml`.
- Every source and test file listed in the SHA-256 table.

## Commands executed and outcomes

All commands were run from `/Users/ahmadmabrouk/Desktop/Veyro` or `backend/` with `backend/.venv/bin/python` (Python 3.14.5).

**CAP-008 binding check**
- `colima status`: running on macOS Virtualization.Framework with the docker runtime, socket `~/.colima/default/docker.sock`.
- `colima version`: 0.10.3.
- Engine via the Colima socket: server 29.5.2, client 29.6.0, `{Name: colima, OS: Ubuntu 24.04.4 LTS}`. This matches the CAP-008 approved binding.
- No Docker Desktop process was running.

**SCN-132 direct run**
- `pytest -v app/modules/{six}/tests/test_scaffold_live.py`: 6 passed. Node IDs:
  - `app/modules/membership/tests/test_scaffold_live.py::test_scaffold_live`
  - `app/modules/booking/tests/test_scaffold_live.py::test_scaffold_live`
  - `app/modules/payment/tests/test_scaffold_live.py::test_scaffold_live`
  - `app/modules/ledger/tests/test_scaffold_live.py::test_scaffold_live`
  - `app/modules/pos/tests/test_scaffold_live.py::test_scaffold_live`
  - `app/modules/access/tests/test_scaffold_live.py::test_scaffold_live`

**Default runner (`pytest --collect-only -q`, no path arguments)**
- 174 tests collected.
- None of the six `app/modules/...` node IDs is collected directly, because `testpaths = ["tests"]`.
- The six are executed only inside the `tests/contract/test_domain_scaffold_inventory.py::test_all_six_domain_scaffolds_pass` subprocess.
- I reproduced that inner command with `--junitxml`. It contains exactly the six testcases, classnames `app.modules.<domain>.tests.test_scaffold_live`, name `test_scaffold_live`, all passed.

**Full backend suite**
- `pytest -q -rA`: **174 passed** (21.39s).
- Both inventory tests and both financial-invariant tests PASSED.

**`run_regression.py`**
- It contains no pytest entry point; it is a governance aggregate.
- Result: AGGREGATE PASS 4/4, 1 N/A (CAP-007 retired).
- It wrote `knowledge/05-QA/tools/regression-runs/RUN_20261003T111853Z.txt` into the repo. I removed that one file afterwards (see the git-status section) and kept a copy at `/tmp/slice7-drill-tools/RUN_20261003T111853Z.txt`.

**Lint and type checks**
- `ruff check --no-cache .`: all checks passed.
- `ruff format --check` on the 25 Slice-7 files: all already formatted.
- Repo-wide `ruff format --check`: 7 files would be reformatted (`authn.py`, `migration_safety.py`, `postgres.py`, `tenant_isolation.py`, `test_architecture_gate_rls.py`, `test_authn_harness.py`, `test_migration_safety_harness.py`). None of them is a Slice-7 file.
- `mypy app tests` (strict, cache in /tmp): success, 47 source files.

**Governance validators**

| Validator | Result |
|---|---|
| `verify_baselines.py` | PASS, 4/4 |
| `validate_capabilities.py` | PASS, 7 |
| `capability_drift_check.py` | PASS, 8, no drift |
| `validate_repo_skeleton.py` | PASS, 7/7 |
| `validate_baseline_binding.py` | PASS |
| `validate_migration_ordering.py` | PASS |
| `validate_capability_manifest.py` | PASS, 9 |
| `validate_architecture_gates.py --gate module-deps` | `GATE_NOT_IMPLEMENTED` (unchanged, never PASS) |

**`git diff --check`**
- Scoped to `backend/app/modules`, `backend/tests/contract` and `tests/harness/tenant_context.py`: clean.
- Unscoped: **fails**, `knowledge/05-QA/BUG_REGISTRY.md:317: new blank line at EOF`. HEAD's copy ends with a single newline, so this comes from the working tree. See NF-6.

**Model-routing attestations (`mr_verify.py`)**
- Implementer transcript `1bba8cd1-….jsonl` as `sonnet veyro-implementer`: PASS, 150 turns, 100% `claude-sonnet-5`.
- Reviewer transcript `…/subagents/agent-a4018a8a551393f5c.jsonl` as `opus veyro-code-reviewer`: PASS, 35 turns, 100% `claude-opus-5-5`. Its `.meta.json` has `agentType: veyro-code-reviewer`.

**Containers after the run:** no leftover harness container. Only the pre-existing unrelated `frosty_bhabha` container is present (see Observations).

## SCN-MOD001-132 results

**Positive case: PASS.** All six scaffolds pass directly and through the inventory. Each one:
- runs `SELECT 1` on a real disposable Postgres via CAP-008;
- resolves a `uuid4` tenant through the shared `TenantContext` contract and the test-only resolver.

The six files have the same shape apart from the domain name.

**Default-runner note (not a finding):** the six are not collected as node IDs by the default runner. They run only through the inventory subprocess, which is part of the default run. So SCN-132's "CI test-run step reports a non-zero exit" property holds locally, through the inventory test.

**Fail-closed drill.** Run on a throwaway `rsync` copy at `/tmp/slice7-drill/backend`. A sentinel confirmed imports resolved from the copy; the copy was deleted afterwards.

| # | Variant | Outer result | Message / domain named |
|---|---|---|---|
| A0 | unmodified | 2 passed | — |
| a | delete payment file | **FAIL** | `missing domain scaffold(s): ['payment']`; second test lists all six `NOT_COLLECTED` (inner exit 4) |
| h | delete whole `access/` dir | **FAIL** | `['access']` named by the paths test |
| b1 | syntax error in booking | **FAIL** | inner exit 2, all six `NOT_COLLECTED`; booking appears only in the attached stdout tail (3 lines) |
| b2 | ledger assert changed to fail | **FAIL** | `{'ledger': 'failed'}` |
| c | pos file renamed to `scaffold_live_check.py` | **FAIL** | `['pos']` missing |
| c2 | pos file renamed to `test_scaffold_live_v2.py` | **FAIL** | `['pos']` missing |
| d1 | `@skip` on access | **FAIL** | `{'access': 'skipped'}` (inner exit 0) |
| d2 | `@xfail` non-strict on a passing body (XPASS) | green | body really ran and passed; if it ever fails it becomes XFAIL, which d3 shows is caught. Not a finding |
| d3 | `@xfail` on a failing body | **FAIL** | `{'access': 'skipped'}` |
| d4 | empty membership module | **FAIL** | `{'membership': 'NOT_COLLECTED'}` |
| d5 | zero tests (function renamed) | **FAIL** | `{'membership': 'NOT_COLLECTED'}` |
| d6 | module-level `pytest.skip(allow_module_level=True)` | **FAIL** | `{'booking': 'NOT_COLLECTED'}` |
| d7 | `pytestmark = skip` | **FAIL** | `{'booking': 'skipped'}` |
| e1 | real test `@skip` + passing sibling defined **after** it | **GREEN (false clean)** | inner run "1 passed, 1 skipped" for ledger; inventory passes. **NF-3** |
| e2 | same, sibling defined **before** it | **FAIL** | `{'ledger': 'skipped'}` (shows the result depends on order) |
| f | hollow body (`pass`, no DB or resolver) | green | NF-7 |
| g | domain `conftest.py` overrides `scaffold_db` with a fake | green | NF-7 |
| i | inventory's own `DOMAINS` tuple cut to five | green | NF-7 |

All four variant classes in the brief fail closed: (a) delete, (b) break, (c) rename, and (d) skip/xfail/empty/zero tests. My first attempts at e2 and d6 were invalid because I put code above `from __future__`. Both were re-run correctly; the corrected results are shown above.

## SCN-MOD001-133 results

The probes imported the function from the throwaway copy with `-B` (no bytecode written).

**Literal contract**
- P1, balanced Dr100/Cr100: PASS.
- P2, unmatched debit Dr10 alone: `DEBITS_NE_CREDITS: total debits 10 != total credits 0 across 1 leg(s)`.
- In-repo `test_balanced_synthetic_entries_pass` and `test_unbalanced_synthetic_entry_fails_closed` both PASS.

**Adversarial probes**

| Probe | Result | Assessment |
|---|---|---|
| P3 Dr10 + Cr5 + Cr5 | balanced | correct |
| P4 Dr10 + Dr−10 (BUG-050 shape) | rejected at construction (`ValueError` strictly positive) | correct |
| P5 zero amounts | rejected at construction | correct |
| P6 negative amounts | rejected at construction | correct |
| P7 / P7b NaN, sNaN | rejected (`InvalidOperation`) | fails closed, but by accident (wrong exception class) |
| **P8 Dr Infinity + Dr 5 vs Cr Infinity** | **balanced** | **false clean; the unmatched debit of 5 is hidden. NF-1(a)** |
| P8b Dr Inf vs Cr Inf | balanced | non-finite amount accepted. NF-1(a) |
| P9 / P9b float amounts | `TypeError` | fails closed |
| P9c int amounts | balanced | type laxity, no false clean |
| P9d bool `True` as amount | balanced against Decimal 1 | type laxity, no false clean |
| P10 Decimal 0.1 + 0.2 vs 0.3 | balanced | correct |
| P10b 10.00 vs 10 | balanced | correct |
| P10c 10.001 vs 10.00 | violation | correct |
| **P11 extra leg with `side="debit"` (str), amount 999** | **balanced** | **false clean. NF-1(b)** |
| P11b `side=None` | balanced | NF-1(b) |
| P11c foreign enum `Fake.DEBIT` | balanced | NF-1(b) |
| **P11d a lone unmatched debit with `side="debit"`** | **balanced** | **SCN-133's own negative case reported clean. NF-1(b)** |
| P12 duplicate identical legs (balanced) | balanced | aggregate-only, as documented |
| P12b duplicate debit | violation | correct |
| P13 swapped leg order | balanced | correct |
| P14 empty set `[]` | balanced (vacuous) | NF-2 |
| P15 single credit leg | violation | correct |
| P16 same-account self-posting | balanced | pairing not in scope (documented) |
| P17 amount `'10'` (str) | `TypeError` | fails closed |
| P18 `object.__setattr__` bypassing the frozen dataclass | balanced | outside the model; not a finding |

Currency mixing does not apply: the contract has no currency field, and I make no demand for one.

**Mutation kill-check.** Run on the throwaway copy against the two in-repo tests.

| Mutant | Result |
|---|---|
| M1 revert to the pre-fix net signed sum | KILLED |
| **M2 drop the positive-amount validation** | **SURVIVED.** Executed: Dr10 + Dr−10 then reports **CLEAN**, which is the exact BUG-050 counterexample regressing |
| M3 compare absolute values | SURVIVED (equivalent while M2's validation is present) |
| **M2+M3** | **SURVIVED** |
| **M4 one-directional check (`debits > credits` only)** | **SURVIVED.** Executed: a lone unmatched credit then reports **CLEAN** |
| M5 one-directional check (`debits < credits` only) | KILLED |
| **M6 allow zero (`<=` changed to `<`)** | **SURVIVED** |
| M7 ignore side entirely | KILLED |
| M8 credits summed from DEBIT legs | KILLED |
| M9 invariant label removed from message | KILLED |
| M10 raise replaced by return | KILLED |
| **M11 side-signed sum with validation dropped** | **SURVIVED** |
| **M12 balanced fixture emptied (vacuous positive)** | **SURVIVED** |

**Score: 6 killed, 7 survived.** The original file was restored and re-ran 2 passed before the copy was deleted.

None of the records claims real ledger business logic. The test docstring explicitly calls itself a placeholder. No overclaim found.

## Pre-fix code-review findings: status now

| CR finding | Status now | Evidence |
|---|---|---|
| P1-1 signed-sum, not debits vs credits | **FIXED** for the reviewer's counterexamples (P1, P4 and P12b behave correctly). It is **not regression-locked** (M2/M11 survive), and adjacent false-clean paths remain (NF-1). | probes, mutants |
| P2-1 test resolver in production `_shared/` | **FIXED.** `_shared/tenant_context.py` holds only `TenantContext` and the Protocol. `StaticTenantContextResolver` exists only at `tests/harness/tenant_context.py:17`. | grep |
| P2-2 `Conn` imported from the critical `tenant_isolation` module | **FIXED.** No `tenant_isolation` import in any Slice-7 file; `Conn` comes from `app.modules.conftest`. | grep |
| P2-3 deletion makes all six report `NOT_COLLECTED` | **STILL PRESENT**, disclosed as not fixed. The record calls it "intentional conservative" behaviour. It also applies to collection/syntax errors (drill b1), which the record does not mention. The inventory docstring overstates it (NF-5). | drills a, b1 |
| P2-4 `ruff format` | **FIXED** for all 25 Slice-7 files. | ruff |
| P2-5 depends on uncommitted CAP-008 `postgres.py` | **STILL PRESENT**, accurately disclosed. `postgres.py` is still `M` (mtime Oct 2, before the slice). Slice 7 did not modify it and contains no `docker` invocation of its own. | git status, stat |
| P2-6 CAP-008 registry text names only the tenant-isolation/authn harness | **STILL PRESENT**, accurately disclosed. Registry line 23 is unchanged. I agree the use is within the approved binding: same entrypoint, same pinned digest, loopback, synthetic data only. | registry |

## New findings (this security gate)

**NF-1 · P1 · False clean in the financial invariant for legs outside the modeled domain**
- **Where:** `backend/tests/contract/test_financial_invariant_scaffold.py:38-40` and `:51-52`. `__post_init__` checks only `amount <= 0`. The two sums filter on `side is Side.DEBIT` and `side is Side.CREDIT`, with no else-branch.
- **Path (a):** `Decimal("Infinity")` passes the type check, passes mypy and is "strictly positive". Dr Infinity + Dr 5 vs Cr Infinity reports balanced (P8), hiding an unmatched debit of 5.
- **Path (b):** any `side` that isn't a `Side` member (`"debit"`, `None`, a look-alike enum) is silently dropped from both totals. A lone unmatched debit expressed as `side="debit"` reports balanced (P11d). That is SCN-133's own negative case returning clean.
- **Mitigations:** mypy strict would flag a typed `str` literal for `side`. No CI gate enforces mypy, and fixtures built from untyped or parsed data would bypass it. Path (a) has no static mitigation at all.
- **Why P1:** both paths are false cleans of the named `DEBITS_NE_CREDITS` invariant, the same defect class as BUG-050. This harness is the template the future ledger module inherits. I note the exposure is limited to test-authored synthetic data; the lead may weigh that, but by this review's rubric it is P1.
- **Fix (mechanical, still placeholder-only):** in `__post_init__`, require `isinstance(self.side, Side)`, `isinstance(self.amount, Decimal)`, and `self.amount.is_finite()`, raising a named error. Optionally, raise on an unknown side inside the checker too.

**NF-2 · P2 · The BUG-050 fix is not regression-locked (7 surviving mutants)**
- **Where:** `test_financial_invariant_scaffold.py:75-87`. There are only two tests.
- **Executed impact:**
  - M2 (validation dropped) brings back the exact BUG-050 false clean (Dr10 + Dr−10 reports CLEAN) with the suite green.
  - M4 (one-directional check) lets a lone unmatched credit report CLEAN.
  - M6, M11 and M12 also survive. M12 shows the positive test passes vacuously on an empty set (P14).
- **Fix:** add regression tests for:
  - the reviewer's two counterexamples;
  - an unmatched-credit case;
  - rejection of zero, negative, NaN, Infinity and non-`Side` inputs;
  - a non-empty assertion on the balanced fixture.

  The CR already suggested the first item ("add the two probes above as regression cases"); it was not done.

**NF-3 · P2 · Inventory aggregation is last-wins, so a skipped scaffold can be masked**
- **Where:** `backend/tests/contract/test_domain_scaffold_inventory.py:76-88`. `report[domain]` is overwritten for each testcase.
- **What happens (drill e1):** `test_scaffold_live` skipped plus a passing sibling test defined after it gives an inner run of "1 passed, 1 skipped" for ledger, inner exit 0, and a **green** inventory. That domain's harness proof never ran.
- **Why it matters:** this defeats the skip detection the Slice-7 record claims ("naming any individual failing/missing/skipped domain"). The result also depends on definition order (e2 fails).
- **Fix:** keep the worst status per domain, and require exactly one testcase named `test_scaffold_live` per domain.

**NF-4 · P2 · Bootstrap state files contradict the attestation evidence**
- **Where:**
  - `knowledge/00-System/CURRENT_STATE.md:26` says "self-report tier only — no `mr_verify.py` transcript attestation exists for this Claude Code session or its subagents".
  - `knowledge/00-System/CURRENT_HANDOFF.md:25` says "self-report only — no `mr_verify.py` transcript exists for a Claude Code session".
- **Evidence:** I ran `mr_verify.py` myself. Both transcripts exist and both attest PASS: implementer 150/150 `claude-sonnet-5`, code reviewer 35/35 `claude-opus-5-5`. The Slice-7 record, BUG-050 and the CR doc were corrected; these two files were not.
- **Why P2:** these are the files every session reads first, and they now misstate a model-assurance fact that drives routing decisions. It understates rather than overstates assurance, so it is not P1, but it must be reconciled before promotion.

**NF-5 · P3 · Inventory docstring overstates what the second test names**
- **Where:** `test_domain_scaffold_inventory.py:12-18` says deleting or breaking a scaffold makes `test_all_six_domain_scaffolds_pass` name "exactly that domain".
- **Actual behaviour:** for deletion, rename or a collection/syntax error, it reports all six `NOT_COLLECTED` (drills a, b1, c). The domain is named only by the companion paths test, or for a syntax error only in the stdout tail. Only an assertion failure (b2) names exactly that domain.

**NF-6 · P3 · "`git diff --check` clean" claim is inaccurate as stated**
- **Where:** `CURRENT_STATE.md:26` and `CURRENT_HANDOFF.md:27` say `git diff --check` is clean, with no scope.
- **Actual:** an unscoped run fails on `BUG_REGISTRY.md:317` (trailing blank line at EOF in the working tree; HEAD ends with a single newline). The Slice-7 record's scoped command is accurate and is clean.

**NF-7 · P3 · The inventory checks outcomes by name, not content**
- **What stays green:** a hollow body (f), a domain-level `conftest.py` that replaces `scaffold_db` with a fake (g), and an edit to the inventory's own `DOMAINS` tuple (i).
- **Why only P3:** any test-level check has this limit when its own files can be edited.
- **Recommendation:** a cheap static assertion that each scaffold requests `scaffold_db` and imports the shared resolver, and that no `conftest.py` exists under `app/modules/<domain>/tests/`. Pin `DOMAINS` against the `IMPLEMENTATION.md` topology.

## Observations (no finding)

- **Co-tenant container (carried forward, not new):** `frosty_bhabha` (`mikeh1975/tradingview-mcp:latest`, an unpinned third-party image) is still running on the CAP-008 Colima engine's default bridge. This is the same container as R5's NR5-5, still unrecorded in CAP-008 evidence. Slice 7 adds another `disposable_postgres()` consumer on that bridge, still with a random per-run password and synthetic data only. Recommendation unchanged: record it in CAP-008 evidence, or isolate `disposable_postgres()` on a per-run `--internal` network through a separately governed change. Nothing in Veyro treats it as trusted. I did not touch it.
- **Superuser DSN for the scaffold probe:** `app/modules/conftest.py:33` connects as the container superuser, used only for `SELECT 1`. This makes no isolation claim, so it is acceptable for a liveness probe. The real domain suites must use the runtime role.
- **Role label in `mr_verify` is caller-supplied:** for the lead transcript there is no `.meta.json` to bind the role, so the Sonnet tier is verified but the `veyro-implementer` role label is asserted. The subagent's `.meta.json` does confirm `veyro-code-reviewer`.
- **No credentials or member data:** no secrets in any Slice-7 file; tenants are `uuid4` values and accounts are named `synthetic:*`.
- **Python version:** the venv runs 3.14.5 and `pyproject` requires 3.13 or later. Consistent.

## Model routing and capability integrity

- **Build routing:** Sonnet, attested 150/150 `claude-sonnet-5`. This conforms to SCN-132's mechanical-run tier and to the routine-not-critical classification. The slice does not modify or duplicate the ADR-005 Decision 1 critical harness: `tenant_isolation.py` mtime is Sep 29, `postgres.py` and `authn.py` mtimes are Oct 2, and there are no imports from `tenant_isolation`.
- **Code review:** Opus, attested 35/35. That review does not satisfy SCN-132/133's `veyro-security-reviewer` routing; this review is that gate.
- **CAP-008:** used within the approved binding. Colima 0.10.3, engine 29.5.2, CLI 29.6.0, identity `colima`/Ubuntu 24.04.4, loopback publish, only through `disposable_postgres()`, no Docker Desktop. P2-6's registry wording gap persists (P3-level; already tracked).
- **No new capability or dependency:** `pyproject.toml` is unchanged. Slice-7 imports are stdlib, `psycopg`, `pytest` and in-repo modules only. No unregistered tool.
- **Owner-reserved restrictions:** no spend, no real member data, no deploy, no scope change.

## Evidence-accuracy check

**Accurate, independently matched:**
- 174/174 backend tests.
- mypy 47 source files.
- 25 Slice-7 files formatter-clean.
- 6/6 direct scaffold runs.
- The reviewer's two counterexamples now behave correctly.
- All validators PASS; `module-deps` reports `GATE_NOT_IMPLEMENTED`.
- The attestation counts in the Slice-7 record, BUG-050 and the CR (150 and 35 turns).
- BUG-050's status: OPEN, pending this review.

**Inaccurate or overstated:**
- NF-4: CURRENT_STATE and CURRENT_HANDOFF still deny the attestation.
- NF-6: unscoped "`git diff --check` clean".
- NF-5: inventory docstring.
- The Slice-7 record's claim that the inventory names "any … skipped domain" (NF-3 shows a masking path).
- The record's and BUG-050's framing that the fix is complete, without disclosing that nothing pins it (NF-2).

**TEST_RESULTS.md:** has no Slice-7, SCN-132 or SCN-133 entry. That is consistent with both scenarios being NOT EXECUTED and unpromoted, so it is not a finding.

## SHA-256 (at review time)

| File | SHA-256 |
|---|---|
| backend/app/modules/_shared/tenant_context.py | 54cd64413d8d034307809aa9d529e931b448290749941d44b2d861c40d21b815 |
| backend/app/modules/conftest.py | c6ecb7bbdfa81e401a73afa12b1023598de6652fbac57d6a532a11a8017c6ca5 |
| backend/app/modules/membership/__init__.py | 02a99e3da3e63ba416c4581052fd2310a97a8dd7def6c088317de2af4431bbe2 |
| backend/app/modules/booking/__init__.py | 05a91e77f7cf0db0a489501169a6d8d94c53817ab4e36dfaf3a2eb3dedd0edc1 |
| backend/app/modules/payment/__init__.py | b46e543aff37b4202046d4b9aadd63f2c58e3615fc88ae33f1c3ad7bbdd9f33c |
| backend/app/modules/ledger/__init__.py | d195bba894148afff33749770075fe0140a93981a8c02e3184a2b014c4667056 |
| backend/app/modules/pos/__init__.py | 120bec222281bc9a28a22cf341c707911b4fa6a5dbdcab89095ef343b88435b0 |
| backend/app/modules/access/__init__.py | 9e1699e09f34f604455630dcdc9a354608dfc54c08e163c2126df2a60d08b3c9 |
| backend/app/modules/{all six}/tests/__init__.py (identical) | e8ceb79a24e08ec5193097e8b33827d46bf4ba14f18513e9adc21bb3461691c9 |
| backend/app/modules/membership/tests/test_scaffold_live.py | df3cc7605b83290b38526e6edd5825c9c151a535dcf6d8eee2c9485eed355780 |
| backend/app/modules/booking/tests/test_scaffold_live.py | 43e81661893b9ec813e6e55415e0f228991dbfc9475704e44dcd3fb77a51ce14 |
| backend/app/modules/payment/tests/test_scaffold_live.py | 4e2344d51e74fcb0e7a892a25b8feaf58e3db8d7f65b07e7d25f738e8fcb1146 |
| backend/app/modules/ledger/tests/test_scaffold_live.py | 68301898afee50bed8b70cb3b62a5afb7259a48569026c888e0787f353eb8c42 |
| backend/app/modules/pos/tests/test_scaffold_live.py | 009fb0a4c36b360fd809c76f7488a3bb3b298835773269802743c860be1e916b |
| backend/app/modules/access/tests/test_scaffold_live.py | c28f6f3b82c88c5dbd67dc2e82d01580d0109284cb17f3b9b9abf6a51f0ceec8 |
| backend/tests/harness/tenant_context.py | daf9a22510f68e35747bc785ec3e1729e42c46a12153eb934f18879b6d993434 |
| backend/tests/contract/test_domain_scaffold_inventory.py | 1a40dcdbd967dae688f4106399669b8135be98c08cc4fd6019f8401c3fe8c4ec |
| backend/tests/contract/test_financial_invariant_scaffold.py | 17a6eb24a1240877b70a62e1d473d12d05a3e0001fdf60205f42301413cbab96 |
| backend/tests/harness/postgres.py (reused, not reviewed for change) | 3e4c7d451aaa23e1bfec42a1c7d4e8774eecb72eafec0f2f35b842a4cf1f5f67 |
| backend/pyproject.toml | 039332c96ab93d82de930d1c84e3351a160829604126868da3a2a8fdfdd40695 |
| SLICE-7-gov01-r02-domain-suite-scaffolds-financial-invariant-2026-10-03.md | a5fd810481d696a82845a35e247bb11fdc71dcde3b6977df4d67741b94b09ae8 |
| BUG-050-financial-invariant-placeholder-false-clean.md | 00978d38bb305e4fe864444f7c7996e0433cdba5e7f0f047c2dfcc59e041547c |
| CR-MOD001-GOV01-R02-DOMAIN-SCAFFOLDS-2026-10-03.md | 358a60e61c5078ba5ab5fe3b3ba7d58987aa428f586a10e9adcc8e78affd3206 |
| Implementer transcript 1bba8cd1-….jsonl | b139f557cca3cfa9271fcd33cd6988412988736ba8b388d66933e437f21df4c5 |
| Code-reviewer transcript agent-a4018a8a551393f5c.jsonl | f481c8bd6c002a481bab61b274b164258c47f3f1fbfb7ed4aaafc0c2adb15b56 |
| /tmp/slice7-drill-tools/drill132.sh | 47d4edd4ba066108a655690d23b5b942f3606603e5109d7f760616e8fe8277f9 |
| /tmp/slice7-drill-tools/drill132b.sh | 441e30408cbd581614c06147533f0f4d0432479b5c2ffecec5f49a26c43d8c9e |
| /tmp/slice7-drill-tools/probe133.py | 897a19ac5a633048054d433b42ad24df190a19580c40358cf69554d5a9102bc3 |
| /tmp/slice7-drill-tools/mut133.py | b3562c9e27cee7fa701df28844424699ab0c600e75b7412e7716430acd34ab85 |

## git-status preservation

The final `git status --porcelain | diff - /tmp/veyro_status_before.txt` is **empty** (identical to baseline). HEAD is unchanged at `e516bedabf3d654ad3ae16d948b8f3522739ddc2`.

**Disclosure:** running `knowledge/05-QA/tools/run_regression.py` as documented wrote one new untracked file, `knowledge/05-QA/tools/regression-runs/RUN_20261003T111853Z.txt`; that is how the tool records its run. I removed that one file, which I had created, to restore the baseline. Its content is kept at `/tmp/slice7-drill-tools/RUN_20261003T111853Z.txt`.

No other repo file was created, edited or deleted:
- ruff ran with `--no-cache`, mypy's cache went to `/tmp`, and pytest ran with `-p no:cacheprovider`;
- all mutations and drills ran only in `/tmp/slice7-drill`, which has been deleted;
- no scenario or bug status was changed, and nothing was committed.

## Verdict and eligibility

**BLOCKED.** P0=0, P1=1 (NF-1), P2=3 (NF-2, NF-3, NF-4), P3=3 (NF-5, NF-6, NF-7).

BUG-050 closure and SCN-MOD001-132/133 promotion are **NOT eligible**.
- SCN-133 needs NF-1 and NF-2 fixed.
- SCN-132 needs NF-3 fixed.
- Both need NF-4 reconciled.
- Each fix then needs a fresh independent `veyro-security-reviewer`/Opus re-review that re-runs this drill set and mutant set.

BUG-050 should stay OPEN: its fix is real but incomplete. NF-1 is the same false-clean class and NF-2 leaves the original fix unpinned.

---

## Orchestrator addendum (not part of the reviewer's report; appended by the orchestrating Opus session `4deb36b1-1097-4101-9b1c-8f1354e4469c`)

Everything above this rule is the reviewer's report exactly as returned, except the two `Reviewer transcript` lines, which the orchestrator filled in as the report instructed. The orchestrator independently checked the following:

- **Baselines:** `verify_baselines.py` returned PASS 4/4 before the review was delegated.
- **Earlier transcripts:** the orchestrator re-ran `mr_verify.py` on the code-reviewer transcript (`agent-a4018a8a551393f5c.jsonl`) and got PASS, 35 turns, 100% `claude-opus-5-5`. The reviewer separately verified the implementer transcript (150/150 `claude-sonnet-5`).
- **This reviewer's transcript:** `mr_verify.py` returned PASS (97 turns, 100% `claude-opus-5-5`). The `.meta.json` file gives `agentType: veyro-security-reviewer`. This reviewer is a fresh subagent. It had no part in implementing this slice or in the pre-fix code review (agentId `a531c4e0da8f0338c`, which is not `a4018a8a551393f5c`).
- **NF-1 reproduction:** the orchestrator ran its own read-only `python -B` reproduction against the in-repo `test_financial_invariant_scaffold.py`. Both cases reported CLEAN, which is a false clean:
  - Path (a): Dr Infinity + Dr 5 vs Cr Infinity.
  - Path (b): a lone Dr 10 with `side="debit"`.
- **Code reading:** lines 37-39 and 50-51 have no `Side` type check and no `is_finite()` check, which matches NF-1.
- **Working tree:** `git status --porcelain` was identical to the pre-review snapshot after the reviewer finished. The only change before this report was written is this report file itself.
- **Scope:**
  - Nothing was changed in code, scenario or bug status, R04, ADR-010 or SCN-067.
  - Nothing was committed or pushed.
  - BUG-050 stays OPEN, and SCN-MOD001-132/133 stay unpromoted.
  - No credit was given for R04, SCN-067, SCN-059/066/070/113 or CI.
- **Evidence integrity:** the first run of `evidence_integrity_check.py` on this report failed. It reported one BROKEN REFERENCE, the reviewer-deleted `knowledge/05-QA/tools/regression-runs/RUN_20261003T111853Z.txt`.
  - **What the orchestrator did:** it restored that genuine run artifact byte-for-byte from the reviewer's kept copy (sha256 `2c09020fada76225e07ef65b09cd7960924598d03c517e824d9883ab80d368e8`, identical in both places). Leaving run logs untracked in that directory matches the existing convention.
  - **Re-run result:** PASS, 363 files scanned, no broken references.
- **Final working-tree delta:** compared with the pre-review snapshot, two untracked files are new: this report and that run artifact.
- **NF-4 and NF-6 are still open:** the orchestrator deliberately did not fix them in this read-only gate. The remediation session has to reconcile them.

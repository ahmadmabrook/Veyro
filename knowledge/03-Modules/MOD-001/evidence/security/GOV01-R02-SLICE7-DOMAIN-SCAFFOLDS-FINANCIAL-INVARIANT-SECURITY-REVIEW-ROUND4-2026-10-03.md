---
doc: GOV01-R02-SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT-SECURITY-REVIEW-ROUND4-2026-10-03
date: 2026-10-03
module: MOD-001
requirement: GOV-01-R02 (routine portion — six domain-suite scaffolds + financial-invariant placeholder)
scenarios: SCN-MOD001-132, SCN-MOD001-133
reviewer_role: veyro-security-reviewer (fresh context, round 4; did not implement, code-review, or previously security-review this slice)
model: claude-opus-5
verdict: BLOCKED
p0: 0
p1: 0
p2: 1
p3: 2
---

# Slice 7 round-4 independent security re-review: domain scaffolds and financial-invariant placeholder

## Session / model identity (stated plainly for independent verification)

- Reviewer transcript: `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/136d306b-68c0-44cb-a6f4-cbbb36ab6acc/subagents/agent-aeaba800449744248.jsonl`
- Orchestrator session `136d306b-68c0-44cb-a6f4-cbbb36ab6acc`; agentId `aeaba800449744248`.
- `.meta.json` contents, quoted verbatim: `{"agentType":"veyro-security-reviewer","description":"MOD-001 Slice-7 round-4 security re-review","toolUseId":"toolu_01YK4nWdA9KzqT4PSE3qEJ7S","spawnDepth":1,"requestShape":"foreground","requestNonInteractive":true}`
- **Disclosed, not glossed:** unlike round 2's `a531c4e0da8f0338c` and round 3's `a158668cf68bdfeea`, this agent's `.meta.json` carries **no `model` key**. The `agentType` role label is bound by the meta file; the *tier* is therefore attested only by the per-turn `model` field inside the JSONL, which is exactly the signal `mr_verify.py` reads. A direct read of that field at the time of writing shows **79 turns carrying a model id, 100% `claude-opus-5`, no second id and no fallback**. My own environment reports me as `claude-opus-5`.
- **I did not run `mr_verify.py` on my own transcript as a self-attestation, and I make no claim about its verdict.** The orchestrator is to run `backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <the path above> opus veyro-security-reviewer` and record the result. The raw model-field count above is a direct observation, not a substitute for that tool's verdict.
- agentId `aeaba800449744248` is distinct from the implementer session, the code reviewer (`a4018a8a551393f5c`), round 2 (`a531c4e0da8f0338c`) and round 3 (`a158668cf68bdfeea`). No self-approval: I did not author, remediate, or previously review any part of this slice.

## Verdict: BLOCKED (P0=0, P1=0, P2=1, P3=2)

**Round 3's blocking finding NR3-1 is genuinely and substantively fixed.** I did not take this from the remediation record — I re-executed round 3's N1/N2/N3 precision counterexamples against the current code, re-ran the complete M1-M15 mutant set, added nine new mutants aimed at the `localcontext()`/`Inexact` remediation itself, and then ran a 60,000-case randomized differential fuzz against an exact `Fraction` oracle. **Zero false cleans were found in current code, in any probe.** That is a materially stronger result than rounds 1-3 ever had on this function, and it is the first round in which the false-clean *behaviour* of `assert_debits_equal_credits` survives adversarial search.

What blocks is not behaviour — it is that **the NR3-1 fix is only half pinned**. The two new regression rows both place the excess leg on the **debit** side, and both pin a specific magnitude rather than the guard's mechanism. Two mutants therefore survive the suite, and **each one reintroduces a false clean of exactly the BUG-050 class**: dropping the trap from the credit-side sum (`Dr 1E+30` vs `Cr 1E+30 + Cr 0.01` reports balanced), and replacing the trap with a precision bump (`Dr 1E+70 + Dr 0.01` vs `Cr 1E+70` reports balanced). Round 3's own stated severity rule caps a surviving mutant at P3 only when it "fails closed in every case and produces no false clean"; neither of these does. Round 2 rated the directly analogous condition — the fix is correct but not regression-locked — at P2 (NF-2). I follow that precedent. This is a one-line-plus-one-row remediation.

Two P3s follow from the same remediation: the new boundary test is tautological (it cannot distinguish the condition it is named for), and the `DEBITS_NE_CREDITS` error code is reused for a condition that is not a debits-not-equal-credits violation at all.

**SCN-MOD001-132 again has no blocking finding of its own.** Every inventory drill, including round 3's e1/e2 and its own new e3/e4, reproduces round 3's result exactly. The block is confined to the SCN-133 file and therefore to BUG-050's closure.

**I report severities and recommendations only. I promoted nothing, closed nothing, and fixed nothing.**

## Scope

**In scope:** `backend/tests/contract/test_financial_invariant_scaffold.py` (round-3 remediated); `backend/tests/contract/test_domain_scaffold_inventory.py`; the six domain scaffolds under `backend/app/modules/{membership,booking,payment,ledger,pos,access}/`; `backend/app/modules/conftest.py`; `backend/app/modules/_shared/tenant_context.py`; `backend/tests/harness/tenant_context.py`; Slice 7's reuse of `disposable_postgres()` inside the approved CAP-008 Colima binding; SCN-132/133 acceptance criteria and negative cases read literally; model routing and capability integrity; the four owner-reserved restrictions; the current status of every round-2 and round-3 finding; and evidence-record accuracy.

**Out of scope, no credit given or withheld:** R04, ADR-010 and Amendment A2, SCN-067, the Anthropic model-assurance safeguard, SCN-059/066/070/113, BUG-048, CAP-008's own qualification (confirmed in-scope use only, not re-litigated), CI wiring beyond what the default local runner collects, and real ledger business logic — SCN-133 is held strictly to its literal placeholder contract. **I did not touch, retry, route around, or evaluate the separately-BLOCKED A2/R04/SCN-067 matter in any way.**

## Inputs read

`knowledge/00-System/SESSION_BOOTSTRAP.md`; `CURRENT_STATE.md` (Slice-7 round-2 and round-3 checkpoints, lines 27-32); `CURRENT_HANDOFF.md` (lines 4-5, 22-28, 30-43); `knowledge/00-System/DEVELOPMENT_CONSTITUTION.md` (full — DC-01/04/06/07/10/12/16/17/19/20/21 and the zero-known-defects rule); `knowledge/00-System/CAPABILITY_POLICY.md` (fail-closed rule, the 11 required supply-chain review fields, first-party/harness exemption); `knowledge/00-System/CAPABILITY_REGISTRY.md` (CAP-005..008 and RULE-001..003 rows); `knowledge/03-Modules/MOD-001/SCENARIOS.md` SCN-MOD001-132 (line 919 onward) and SCN-MOD001-133 (line 958 onward), read literally; the round-2 security review in full; the round-3 security review in full (including its M1-M15 table, drill table, probe table and `/tmp` disclosure); `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-050-financial-invariant-placeholder-false-clean.md`; `knowledge/05-QA/BUG_REGISTRY.md` (front matter and the BUG-050 row, line 206); `knowledge/03-Modules/MOD-001/TEST_RESULTS.md`; `.claude/rules/backend/{architecture,api,database,concurrency,performance}.md`; `.claude/rules/infra/{secrets,release}.md`; `.claude/rules/global/owner-reserved-restrictions.md`, `knowledge-vault-durability.md`, `notion-mcp-scope-discipline.md`; `.claude/rules/admin/admin-privileged-console-baseline.md`; `backend/pyproject.toml`; `backend/tests/harness/postgres.py`; every file in the SHA-256 table below.

## Environment

- Interpreter: `backend/.venv/bin/python` — `Python 3.14.5 (main, May 10 2026, 10:21:34) [Clang 21.0.0 (clang-2100.0.123.102)]`. System `python3` was not used anywhere.
- All mutations, drills and probes ran only in `/tmp/r4-drill` and `/tmp/r4-tools`, never against the real tree. Probes ran with `-B` (no bytecode written), pytest with `-p no:cacheprovider`, ruff with `--no-cache`, mypy with `MYPY_CACHE_DIR=/tmp/r4-mypy`.
- `/tmp/r4-drill` (the throwaway `rsync` backend copy and all mutated module copies) was **deleted at closeout**; `/tmp/r4-tools` retains only the probe scripts, hashed below.

## CAP-008 binding, verified in actual use

```
colima status  -> colima is running using macOS Virtualization.Framework; arch aarch64;
                  runtime docker; mountType virtiofs;
                  docker socket: unix:///Users/ahmadmabrouk/.colima/default/docker.sock
colima version -> colima version 0.10.3 (git commit 00f6c297e92a82c04a4ab507db0a61435650d7e8)
which -a docker -> /usr/local/bin/docker ; /opt/homebrew/bin/docker ; ~/.docker/bin/docker
/opt/homebrew/bin/docker --version -> Docker version 29.6.0, build fb59821d45
```

PATH's *first* `docker` is still the Docker Desktop-installed `/usr/local/bin/docker`, and the harness still correctly ignores PATH: `postgres.py` pins `TRUSTED_DOCKER_CLI = /opt/homebrew/bin/docker`, `TRUSTED_DOCKER_CLI_REALPATH = /opt/homebrew/Cellar/docker/29.6.0/bin/docker`, `TRUSTED_DOCKER_CLI_VERSION = 29.6.0`, and `COLIMA_DOCKER_HOST = unix://~/.colima/default/docker.sock`. The CAP-008 P1-1 ambient-substitution control is demonstrably holding on this machine right now. No capability drift (`capability_drift_check.py` PASS below).

**Live-DB proof** (`/tmp/r4-tools/verify_live.py`, real `disposable_postgres()` run through the pinned route):

```
pinned image: postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
pinned CLI  : /opt/homebrew/bin/docker host: unix:///Users/ahmadmabrouk/.colima/default/docker.sock
container: veyro-mod001-harness-8159d219 host: 127.0.0.1 port: 33384
published ports: 5432/tcp -> 127.0.0.1:33384
image id|config: sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea|postgres@sha256:721873c34ceb...
server_version: 16.15
SELECT 1 -> (1,)
current_user: postgres
container removed on exit (context manager closed)
```

Loopback-only publish, digest-pinned image matching the registry, random per-run password, removed on exit. The six scaffolds are backed by a real Postgres 16.15, not a short-circuit. No harness container was left behind; `docker ps` after the run shows only the pre-existing unrelated `frosty_bhabha` (see Observations) — which I did not touch.

## Commands executed and real output

### Test suites

| Command | Result |
|---|---|
| `backend/.venv/bin/python -m pytest -q -p no:cacheprovider` (full backend, from `backend/`) | **189 passed in 23.58s** |
| `pytest -q` on `tests/contract/test_financial_invariant_scaffold.py` + `test_domain_scaffold_inventory.py` | **19 passed in 1.76s** |
| `pytest -v` on all six `app/modules/<domain>/tests/test_scaffold_live.py` | **6 passed in 1.56s** — node IDs `app/modules/{membership,booking,payment,ledger,pos,access}/tests/test_scaffold_live.py::test_scaffold_live`, all PASSED |

The round-3 remediation's claimed `189/189 (184 + 5 new)` and the focused count both reproduce exactly (the financial file now carries 17 tests, up from round 3's 12; plus 2 inventory tests = 19).

### Lint and type checks (reported as two separate claims, per NR3-3's own lesson)

| Command | Result |
|---|---|
| `ruff check --no-cache .` | **All checks passed!** |
| `ruff format --check --no-cache` on **the two Slice-7 files only** | **2 files already formatted** (exit 0) — **NR3-3 CLOSED** |
| `ruff format --check --no-cache .` **repo-wide** | **7 files would be reformatted, 41 files already formatted** (exit 1) |
| `mypy app tests` (strict) | **Success: no issues found in 47 source files** |

The 7 repo-wide unformatted files are all **pre-existing and non-Slice-7**, enumerated directly from the tool's own output: `tests/harness/authn.py`, `tests/harness/migration_safety.py`, `tests/harness/postgres.py`, `tests/harness/tenant_isolation.py`, `tests/integration/test_architecture_gate_rls.py`, `tests/integration/test_authn_harness.py`, `tests/integration/test_migration_safety_harness.py`. A targeted grep confirms **neither Slice-7 file appears** in that list. This matches round 2's and round 3's "7 pre-existing" count with round 3's eighth (the Slice-7 file) now removed.

### Governance validators

| Validator | Result |
|---|---|
| `knowledge/00-System/verify_baselines.py` | **PASS — all 4 governing baseline hashes match `PROJECT_INDEX.md` exactly** (Blueprint `80f4b381…`, TSD `0d41c8a1…`, EIP `e5b5ec3b…`, design bundle `c96f77ab…`) |
| `knowledge/00-System/validate_capabilities.py` | **PASS** — 7 capabilities, all registered and APPROVED with required fields present, 0 errors |
| `knowledge/05-QA/tools/capability_drift_check.py` | **PASS** — 8 capabilities checked, **no drift** (CAP-008 version/hash unchanged since approval) |
| `tools/validate_repo_skeleton.py` | **PASS** — all 7 required paths present |
| `tools/validate_baseline_binding.py` | **PASS** — all 4 baselines bound, 5 fail-closed conditions checked |
| `tools/validate_migration_ordering.py` | **PASS** — every migration record complete and phase-ordered |
| `tools/validate_capability_manifest.py --manifest …/MOD-001/evidence/module-capabilities.yaml` | **PASS** — 9 IDs, no cyclic dependency, no missing mandatory privileged-surface Rule, 0 errors |
| `tools/validate_capability_manifest.py --manifest …/MOD-000/evidence/module-capabilities.yaml` | **PASS** — 7 IDs, 0 errors |
| `…/phase3/tools/evidence_integrity_check.py` | **PASS** — no broken evidence references beyond expected forward refs across **365 scanned files**, no missing bug linkage |
| `knowledge/05-QA/tools/run_regression.py` | **AGGREGATE RESULT: PASS (4/4 checks passed, 1 N/A excluded)** — `verify_baselines` PASS, `validate_catalog` PASS (0 errors, 1 tracked non-blocking warning), `validate_capabilities` PASS, `evidence_integrity_check` PASS, `test_bash_guard.py` N/A (CAP-007 retired) |
| `tools/validate_architecture_gates.py --gate module-deps` | `GATE_NOT_IMPLEMENTED: module-deps — not implemented in the GOV-01-R04 critical slice; never reported as PASS` (unchanged, correctly not claimed as PASS) |

### `git diff --check` and working-tree preservation

- `git diff --check` **unscoped: clean, exit 0**.
- `git status --porcelain` captured before any work (`/tmp/r4_gitstatus_start.txt`, **191 entries**) and again at closeout (`/tmp/r4_gitstatus_end.txt`). `diff` of the two is **empty — identical to baseline**. HEAD unchanged at `e516bedabf3d654ad3ae16d948b8f3522739ddc2`.
- **Disclosure:** running `run_regression.py` as documented wrote one new untracked run record, named `RUN_20261003T134417Z.txt`, into the tool's own `regression-runs/` output directory — that is how the tool records a run. I removed that one file, which I had created, to restore the baseline, and kept a copy at `/tmp/r4-tools/RUN_20261003T134417Z.txt` (hash in the SHA-256 table). Following round 3's own lesson, this report cites only the `/tmp` path and deliberately does not write out that artifact's in-repo path, so `evidence_integrity_check.py` has no broken reference to resolve. **Verified for real, and disclosed:** my first draft of this report did spell the in-repo path out, and `evidence_integrity_check.py` immediately returned `FAIL — BROKEN REFERENCE` on it. I corrected this report's wording rather than restoring the artifact or suppressing the check, then re-ran the checker to PASS (below). Round 3's warning about this exact trap is therefore independently confirmed as live, not theoretical. That re-run produced a **second** run record, `RUN_20261003T135502Z.txt`; I removed that one too and kept it at `/tmp/r4-tools/RUN_20261003T135502Z.txt` (hash in the SHA-256 table). Both records I created are out of the repo; the output directory is byte-identical to baseline.
- The only intended working-tree delta from this review is this report file itself.

## SCN-MOD001-132 results

**Positive case: PASS.** All six scaffolds pass directly (6 passed) and through the inventory subprocess (2 passed). Each executes `SELECT 1` against a real digest-pinned disposable Postgres via CAP-008 and resolves a `uuid4()` tenant through the `_shared` `TenantContext` value plus the test-only `StaticTenantContextResolver`. None asserts product behaviour, correctly matching the scenario's own "none asserts real product behavior, since none exists".

**Negative case: PASS, both literal forms.** The scenario requires a non-zero exit "naming that specific domain's missing/failing scaffold, rather than silently reporting the suite green with five domains actually collected". Deletion names `['payment']`; a broken assertion names `{'ledger': 'failed'}`.

**Fail-closed drill set** (throwaway `rsync` copy at `/tmp/r4-drill/backend`; sentinel confirmed the inventory resolved `_BACKEND_ROOT` to `/private/tmp/r4-drill/backend` and `payment` to `/private/tmp/r4-drill/backend/app/modules/payment/tests/test_scaffold_live.py`, so imports came from the copy; the copy was restored from the real tree and re-verified green between every variant):

| # | Variant | Outer result | Message / domain named |
|---|---|---|---|
| A0 | unmodified | 2 passed | — |
| a | delete payment file | **FAIL** exit 1 | `missing domain scaffold(s): ['payment']` |
| b1 | syntax error in booking | **FAIL** exit 1 | inner exit 2, all six `EXPECTED_EXACTLY_ONE_GOT_0:[]` (conservative, fail-closed) |
| b2 | ledger assertion changed to always fail | **FAIL** exit 1 | `{'ledger': 'failed'}` (inner exit 1) |
| c | pos renamed `test_scaffold_live_v2.py` | **FAIL** exit 1 | `missing domain scaffold(s): ['pos']` |
| d1 | `@pytest.mark.skip` on access | **FAIL** exit 1 | `{'access': 'skipped'}` (inner exit 0) |
| d6 | module-level `pytest.skip(allow_module_level=True)` on booking | **FAIL** exit 1 | `{'booking': 'EXPECTED_EXACTLY_ONE_GOT_0:[]'}` |
| d7 | `pytestmark = pytest.mark.skip` on booking | **FAIL** exit 1 | `{'booking': 'skipped'}` |
| **e1** | real `test_scaffold_live` `@skip` + passing sibling defined **AFTER** it | **FAIL** exit 1 | **`{'ledger': 'skipped'}`** — NF-3's false clean stays closed |
| **e2** | same, sibling defined **BEFORE** it | **FAIL** exit 1 | **`{'ledger': 'skipped'}`** — identical to e1, so **order-independent** |
| **e3** | `test_scaffold_live` parametrized (names become `test_scaffold_live[n]`) | **FAIL** exit 1 | `{'ledger': 'EXPECTED_EXACTLY_ONE_GOT_0:[]'}` — fails closed |
| **e4** | real one `@skip` + class-based passing duplicate also named `test_scaffold_live` | **FAIL** exit 1 | `{'ledger': "EXPECTED_EXACTLY_ONE_GOT_2:['skipped', 'passed']"}` — the exactly-one rule holds |
| f | hollow body (`pass`, no DB, no resolver) | green | NF-7, disclosed |
| i | inventory's own `DOMAINS` tuple cut to five | green | NF-7, disclosed |
| A1 | restored | 2 passed | — |

Every row reproduces round 3's result **byte-for-byte on the message text**, including the two variants round 3 itself added. `test_domain_scaffold_inventory.py` is byte-identical to round 3 (`ef6d23fa…cafd021a`, unchanged), so this is a re-verification rather than a new review, and it confirms the round-3 remediation did not regress SCN-132's half.

## SCN-MOD001-133 results

**Literal contract: PASS.**
- Balanced synthetic set (`Dr cash 100.00 / Cr revenue 100.00` + `Dr deferred 25.50 / Cr cash 25.50`): balanced.
- Deliberately unbalanced set, a debit with no matching credit: `DEBITS_NE_CREDITS: total debits 10.00 != total credits 0 across 1 leg(s)` — names the specific invariant violated, not a bare assert.
- All 17 in-repo tests in the file pass, including round 3's three new ones.

### Round-3 precision probes, re-run against the CURRENT code

`/tmp/r4-tools/probe_precision.py`. My probe labels the two failure routes separately — `PRECISION-TRAP` (raised from the `except Inexact` handler) versus `COMPARISON` (raised from `total_debits != total_credits`) — because both carry the same `DEBITS_NE_CREDITS` text and are otherwise indistinguishable (see NR4-2/NR4-3).

| Probe | Round-3 result (pre-fix) | Round-4 result (current code) | Assessment |
|---|---|---|---|
| **N1 `Dr 1E+1000 + Dr 5` vs `Cr 1E+1000`** | **BALANCED — false clean** | **VIOLATION[PRECISION-TRAP]** | **NR3-1 FIXED** |
| **N2 `Dr 1E+30 + Dr 0.01` vs `Cr 1E+30`** | **BALANCED — false clean** | **VIOLATION[PRECISION-TRAP]** | **NR3-1 FIXED** |
| **N3 `Dr Decimal("1.0000000000000000000000000001")` vs `Cr Decimal("1")`** | **BALANCED — false clean** | **VIOLATION[PRECISION-TRAP]** | **NR3-1 FIXED** |
| N boundary `Dr 1E+27 + Dr 1` vs `Cr 1E+27` | violation | **VIOLATION[COMPARISON]** `total debits 1000000000000000000000000001 != total credits 1000000000000000000000000000` | correct, and still via the exact-comparison route |
| N boundary+1 `Dr 1E+28 + Dr 1` vs `Cr 1E+28` | n/a | VIOLATION[PRECISION-TRAP] | correct; threshold is exactly the 28-digit context precision |
| N4 `Dr 1E-40` vs `Cr 1E-40` (genuinely equal) | balanced | balanced | correct |
| N5 `Dr 1E-1000000 + Dr 5` vs `Cr 1E-1000000` | violation | VIOLATION[PRECISION-TRAP] | correct |
| GOOD balanced fixture `100.00`/`25.50` | balanced | balanced | **unaffected by the fix** |
| GOOD 40 x `Dr 0.01` vs `Cr 0.40` | balanced | balanced | **unaffected, no accumulation error** |
| GOOD `Dr 0.1 + Dr 0.2` vs `Cr 0.3` | balanced | balanced | **unaffected** |
| GOOD lone unmatched `Dr 10.00` | violation | VIOLATION[COMPARISON] | correct |
| `Dr 1.00` vs `Cr 1` (equal, different exponent) | n/a | balanced | correct |
| `Dr 1E+30` vs `Cr 1000000000000000000000000000000` (equal, different form) | n/a | balanced | correct — `Decimal(0)` as `start` does **not** spuriously trap on a single 31-digit-ideal-exponent leg |
| **CREDIT-SIDE `Dr 1E+30` vs `Cr 1E+30 + Cr 0.01`** | not probed | **VIOLATION[PRECISION-TRAP]** | **the trap fires on the credit sum independently, not only the debit sum** |
| ONE-SIDE only `Dr 100` (credits empty) | n/a | VIOLATION[COMPARISON] `total debits 100 != total credits 0` | correct |
| ONE-SIDE only `Cr 100` (debits empty) | n/a | VIOLATION[COMPARISON] `total debits 0 != total credits 100` | correct — an empty side is not an exemption |
| Overflow `Dr 9.99E+999999` x2 vs same on credit | not probed | VIOLATION[PRECISION-TRAP] | correct — `decimal.Overflow` subclasses `Inexact`, so the existing `except Inexact` catches it; no bare `decimal` exception escapes |
| Subnormal `Dr 1E-1000030` vs `Cr 1E-1000030` (below `Etiny`) | not probed | VIOLATION[PRECISION-TRAP] | correct — `Underflow` also subclasses `Inexact`; fails closed rather than silently flushing to zero |
| Subnormal `Dr 1E-1000000` vs `Cr 1E-1000000` (representable, equal) | not probed | balanced | correct |
| EMPTY leg list `[]` | balanced (vacuous) | balanced (vacuous) | carried forward; pinned only at test level by the non-empty assertion in `test_balanced_synthetic_entries_pass` (see Observations) |
| Caller decimal context after all calls | n/a | `traps[Inexact] = False`, `prec = 28` | **`localcontext()` does not leak the trap to the caller** |

### Independent precision/robustness pass of my own (one level deeper than round 3)

Round 3 found its P2 by probing one level deeper than round 2's fix. I attempted the same against round 3's fix, both analytically and by randomized search.

**Analytic argument the probes then tested:** if neither `sum()` signals `Inexact`, both totals are the *exact* mathematical sums, and `Decimal.__ne__` is exact regardless of context, so the comparison is exact and no imbalance can hide. Every rounding mode discards non-zero digits only when `Inexact` is signalled; discarding zero digits leaves the value unchanged. `Overflow` and `Underflow` both subclass `Inexact`, so they are caught by the existing handler rather than escaping as bare `decimal` exceptions. `InvalidOperation` cannot arise from adding finite positive operands, which `__post_init__` already guarantees. `Decimal(0)` as `start` neither triggers nor suppresses the trap: adding zero is value-preserving, so the ideal-exponent expansion is skipped when it would not fit in precision (confirmed by the `1E+30` vs `1000000000000000000000000000000` probe), while still forcing a single context-bound addition so that even a **single** over-precise leg on a side is caught (confirmed by N3, which has one leg per side). The mechanism is therefore sound in principle.

**Randomized differential fuzz against an exact `Fraction` oracle** (`/tmp/r4-tools/fuzz_oracle.py`, seed 20261003) — 40,000 generated leg sets of 1-12 legs, amounts drawn from six classes including plain two-decimal money, `1E+0`..`1E+60`, `1E-0`..`1E-60`, 20-40-significant-digit values, extreme `1E±900`..`1E±1200`, and large integers up to 10^28; ~45% of cases forced to an exactly-balanced mirror so true-clean cases occur:

```
cases: 40000  reported-balanced: 3445  raised: 36555
FALSE CLEAN (balanced but exactly unequal): 0
false alarm (raised but exactly equal — fail-closed direction): 14550
```

**Zero false cleans in 40,000 adversarial cases.** This is the strongest available evidence that NR3-1's defect class is genuinely closed in current code, and it is the first time this function has been subjected to a differential oracle rather than hand-picked counterexamples.

**Plausible-money restriction** (`/tmp/r4-tools/fuzz_money.py`, seed 7) — 20,000 sets of 1-400 legs, all amounts two-decimal money up to ~10^9, to check the trap is not disruptive on realistic fixtures:

```
plausible-money cases: 20000  balanced:10039 raised:9961  FALSE CLEAN:0  FALSE ALARM:0
```

**Zero false cleans and zero false alarms on realistic data.** The trap is correctly inert for anything a real money fixture would produce, so NR3-1's fix carries no practical cost at this scope. The 14,550 "false alarms" in the unrestricted fuzz are all genuinely-balanced sets whose legs span more than 28 significant digits (e.g. `1E-1176` alongside `9282691825112755333360171087`); they fail **closed**, which is the right direction, but they expose the label problem recorded as NR4-3.

### Mutation kill-check: round 3's full M1-M15 set plus nine new mutants against the remediation itself

Run in the throwaway copy against the current 17-test suite. Baseline unmutated: **17 passed**; restored baseline after the sweep: **17 passed**.

| Mutant | Round 2 | Round 3 | **Round 4** | Determination |
|---|---|---|---|---|
| M1 revert to the pre-fix net signed sum | KILLED | SURVIVED | **SURVIVED** | near-equivalent; **no false clean** — see equivalence run below |
| M2 drop the positive-amount validation | SURVIVED | KILLED | **KILLED** (3 failed) | killed |
| M3 compare absolute values | SURVIVED | SURVIVED | **SURVIVED** | **TRUE EQUIVALENT**, proven by execution below |
| M2+M3 combined | SURVIVED | KILLED | **KILLED** (3 failed) | killed |
| M4 one-directional (`debits > credits` only) | SURVIVED | KILLED | **KILLED** (1 failed) | killed |
| M5 one-directional (`debits < credits` only) | KILLED | KILLED | **KILLED** (1 failed) | killed |
| M6 allow zero (`<=` to `<`) | SURVIVED | KILLED | **KILLED** (1 failed) | killed |
| M7 ignore side entirely | KILLED | KILLED | **KILLED** (3 failed) | killed |
| M8 credits summed from DEBIT legs | KILLED | KILLED | **KILLED** (3 failed) | killed |
| M9 invariant label removed from message | KILLED | KILLED | **KILLED** (3 failed) | killed |
| M10 raise replaced by return | KILLED | KILLED | **KILLED** (3 failed) | killed |
| M11 side-signed sum with validation dropped | SURVIVED | KILLED | **KILLED** (3 failed) | killed |
| M12 balanced fixture emptied (vacuous positive) | SURVIVED | KILLED | **KILLED** (1 failed) | killed |
| M13 drop the `isinstance(side, Side)` guard | n/a | KILLED | **KILLED** (3 failed) | killed |
| **M14 drop the `isinstance(amount, Decimal)` guard** | n/a | **SURVIVED (NR3-2)** | **KILLED (2 failed)** | **NR3-2 CLOSED** by the two new `(Side.DEBIT, 10.0)` / `(Side.DEBIT, 10)` parametrize rows |
| M15 drop the `is_finite()` guard | n/a | KILLED | **KILLED** (2 failed) | killed |
| **T1 remove `ctx.traps[Inexact] = True`** | n/a | n/a | **KILLED** (2 failed) | the trap itself is pinned |
| **T2 remove `localcontext()` + trap entirely (plain sums)** | n/a | n/a | **KILLED** (2 failed) | the whole remediation is pinned |
| **T3 narrow `except Inexact` to `except Overflow`** | n/a | n/a | **KILLED** (2 failed) | the handler's breadth is pinned |
| **T8 swallow the trap (handler zeroes both totals instead of raising)** | n/a | n/a | **KILLED** (2 failed) | the handler must raise |
| **T4 trap `Rounded` instead of `Inexact`** | n/a | n/a | **SURVIVED** | over-fires (stricter); **no false clean** in any probe — not counted as a finding |
| **T9 drop the explicit `start=Decimal(0)`** | n/a | n/a | **SURVIVED** | behaviourally equivalent (`int` 0 start); typing-only difference — not counted as a finding |
| **T5 replace the trap with `ctx.prec = 60`** | n/a | n/a | **SURVIVED** | **produces a false clean — NR4-1** |
| **T6 add `ctx.prec = 27` alongside the trap** | n/a | n/a | **SURVIVED** | converts the boundary case to a precision failure undetected — **NR4-2** |
| **T7 apply the trap to the DEBIT sum only** | n/a | n/a | **SURVIVED** | **produces a false clean — NR4-1** |

**Score: 20 killed, 5 survivors.** Of the five, two (M3, T9) are equivalent, one (T4) is strictly stricter with no false clean, one (M1) is near-equivalent with no false clean, and **two (T5, T7) each reintroduce a false clean** — which is NR4-1.

**Surviving mutants' actual behaviour, executed** (`/tmp/r4-tools/survivor_probe.py`; `FALSE CLEAN` marks a reported-balanced result; the `100.00`/`25.50` row is genuinely balanced in every column and is a true clean, my script's blanket label notwithstanding):

| Case | Unmutated (control) | T7 debit-only trap | T5 prec=60 | T6 prec=27 | T4 trap Rounded |
|---|---|---|---|---|---|
| **credit-side excess `Dr 1E+30` vs `Cr 1E+30 + Cr 0.01`** | VIOLATION[TRAP] | **BALANCED — FALSE CLEAN** | VIOLATION[CMP] | VIOLATION[TRAP] | VIOLATION[TRAP] |
| debit-side excess `Dr 1E+30 + Dr 0.01` vs `Cr 1E+30` | VIOLATION[TRAP] | VIOLATION[TRAP] | VIOLATION[CMP] | VIOLATION[TRAP] | VIOLATION[TRAP] |
| **deep excess `Dr 1E+70 + Dr 0.01` vs `Cr 1E+70`** | VIOLATION[TRAP] | VIOLATION[TRAP] | **BALANCED — FALSE CLEAN** | VIOLATION[TRAP] | VIOLATION[TRAP] |
| **boundary `Dr 1E+27 + Dr 1` vs `Cr 1E+27`** | VIOLATION[**CMP**] | VIOLATION[CMP] | VIOLATION[CMP] | VIOLATION[**TRAP**] | VIOLATION[CMP] |

**Equivalence determined by execution, not argument** (`/tmp/r4-tools/equiv.py` — unmutated versus M1 and M3 over 14 discriminating inputs: the BUG-050 counterexample, the balanced fixture, lone unmatched debit, lone unmatched credit, `Dr10+Cr5+Cr5`, duplicate debit, float/int/str/bool amounts, both precision counterexamples, the boundary case, and the empty set):

- **M3 (`abs()`) is a true equivalent — byte-identical outcomes on all 14 inputs.** `abs()` is the identity on two non-negative sums, so this is not a test-suite gap and I do not count it as a finding. This confirms round 3's determination independently.
- **M1 (net signed sum) differs on exactly 1 of 14** — the credit-side precision case, where it reports `VIOLATION[COMPARISON]` instead of `VIOLATION[PRECISION-TRAP]`. It still **detects** the imbalance (the net sum `1E+30 - 1E+30 - 0.01` needs no rounding, so it lands on `-0.01` exactly), so M1 produces **no false clean** and is at least as strong on that case. Not a finding. This slightly refines round 3's "true equivalent" label for M1, which I record rather than restate.

## Round-3 findings: status now

| Round-3 finding | Status | Evidence |
|---|---|---|
| **NR3-1 (P2) false clean from decimal-context rounding** | **FIXED (behaviour), NOT FULLY REGRESSION-LOCKED** | N1/N2/N3 all now `VIOLATION[PRECISION-TRAP]`; boundary and all known-good cases unaffected; 0 false cleans in 60,000 fuzz cases; T1/T2/T3/T8 all killed. **But T5 and T7 survive and each reintroduce a false clean — NR4-1.** |
| **NR3-2 (P3) `isinstance(amount, Decimal)` guard not regression-locked (M14 survived)** | **FIXED** | M14 now KILLED (2 failed) by the two new parametrize rows `(Side.DEBIT, 10.0)` and `(Side.DEBIT, 10)` |
| **NR3-3 (P3) file no longer formatter-clean; records said "Ruff clean" unqualified** | **FIXED** | `ruff format --check` on the two Slice-7 files: "2 files already formatted", exit 0; repo-wide back to the 7 pre-existing non-Slice-7 files; BUG-050 and `CURRENT_HANDOFF.md` now state `ruff check` and `ruff format --check` as separate claims |

## Round-2 findings: status now (re-verified, not carried on round 3's word)

| Round-2 finding | Status | Evidence |
|---|---|---|
| NF-1 (P1) false clean for non-finite amounts and non-`Side` sides | **FIXED, unregressed** | M13 and M15 both KILLED; `__post_init__` order (Side / Decimal / finite / positive) re-read line by line |
| NF-2 (P2) BUG-050 fix not regression-locked | **FIXED for the round-2 scope** | M2, M2+M3, M4, M6, M11, M12 all KILLED in my own re-run |
| NF-3 (P2) inventory aggregation last-wins masks a skipped scaffold | **FIXED, order-independent** | e1 and e2 both FAIL with `{'ledger': 'skipped'}`; e3/e4 fail closed; file byte-identical to round 3 |
| NF-4 (P2) bootstrap files contradict the attestation evidence | **FIXED** | `CURRENT_STATE.md` and `CURRENT_HANDOFF.md:39` carry dated corrections with turn counts |
| NF-5 (P3) inventory docstring overstates what the second test names | **FIXED** | docstring matches drills a/b1/b2/c exactly, including the conservative all-six case and the NF-7 limitation |
| NF-6 (P3) unscoped `git diff --check` not clean | **FIXED** | unscoped run exits 0 |
| NF-7 (P3) inventory checks outcomes by name, not content | **STILL PRESENT, accurately disclosed** | drills f and i still green, exactly as the docstring states; not blocking |
| CR P2-1 test resolver in production `_shared/` | **FIXED, unregressed** | `_shared/tenant_context.py` holds only `TenantContext` + the `Protocol`; `StaticTenantContextResolver` lives only in `tests/harness/tenant_context.py` |
| CR P2-2 `Conn` imported from the critical `tenant_isolation` module | **FIXED, unregressed** | zero `tenant_isolation` references in any Slice-7 file (grep returned NONE); `Conn` comes from `app.modules.conftest` |
| CR P2-4 `ruff format` clean on all Slice-7 files | **FIXED** (was REGRESSED in round 3) | see NR3-3 above |
| CR P2-5 depends on uncommitted CAP-008 `postgres.py` | STILL PRESENT, accurately disclosed | `postgres.py` still ` M` in `git status`, hash `3e4c7d45…` unchanged from round 3; Slice 7 did not modify it and has no `docker` invocation of its own |
| CR P2-6 CAP-008 registry text names only the tenant-isolation/authn harness | STILL PRESENT, accurately disclosed | registry CAP-008 row still reads "used by `backend/tests/harness/postgres.py` for the MOD-001 GOV-01-R02 tenant-isolation/authn harness"; I agree the second consumer's use is materially inside the approved binding (same entrypoint, same pinned digest, loopback-only, synthetic data only, no scope widening) |

## New findings (round 4)

### NR4-1 · P2 · The NR3-1 precision guard is only half regression-locked; two surviving mutants each reintroduce a BUG-050-class false clean

- **Where:** `backend/tests/contract/test_financial_invariant_scaffold.py:63-77` (the `localcontext()` / `Inexact` block) and `:156-176` (`test_precision_loss_fails_closed`'s two parametrize rows).
- **What the current code does:** correctly. The trap fires independently on both the debit and credit sums — I verified the credit side directly (`Dr 1E+30` vs `Cr 1E+30 + Cr 0.01` raises), and found no false clean in 60,000 fuzz cases. **This finding is not about present behaviour.**
- **What is missing:** both new regression rows place the excess leg on the **debit** side (row 1: `Dr 1E+30 + Dr 0.01` vs `Cr 1E+30`; row 2: a 29-digit **debit** against `Cr 1`), and the boundary test triggers no trap at all. **No test in the suite exercises the credit-side trap, and no test pins the guard's mechanism rather than two specific magnitudes.** Consequently two mutants survive the full 17-test suite:
  - **T7** — apply the trap to the DEBIT sum only, leaving the credit sum outside `localcontext()`: **17 passed (SURVIVED)**, and under it `Dr 1E+30` vs `Cr 1E+30 + Cr 0.01` **reports balanced**, hiding an unmatched credit of 0.01.
  - **T5** — remove the trap and raise `ctx.prec` to 60 instead (a plausible "just use more precision" alternative a future editor might substitute): **17 passed (SURVIVED)**, and under it `Dr 1E+70 + Dr 0.01` vs `Cr 1E+70` **reports balanced**. Round 3's N2 and N3 both still fail under T5, which is precisely why the current rows cannot detect it.
- **Executed evidence:** the mutation table and the four-column survivor table above; both tables come from real `pytest` exits and real probe output, not from reading the diff.
- **Why this is the BUG-050 class and not a cosmetic test gap:** both surviving mutants produce an affirmative "balanced" verdict for a leg set that is not balanced, with every leg a finite, strictly-positive, correctly-typed `Decimal`. That is the exact defect BUG-050 was filed for, the exact defect NF-1 blocked on, and the exact defect NR3-1 blocked on. Round 3's own stated severity rule for the analogous NR3-2 was that it "fails closed in every case and produces **no false clean**, which is why it is P3 and not higher" — neither T5 nor T7 satisfies that condition.
- **Why P2 (and the explicit counter-argument):** round 2 rated the directly analogous condition — the fix is behaviourally right but not regression-locked, with mutants surviving — at **P2 (NF-2)**, and this is the same species applied to half of round 3's own primary fix, in a file that has now produced a false-clean defect in three consecutive rounds and that round 3 itself described as "the template the future ledger module inherits." Round 3's remediation instruction was explicitly "add a regression test so the guard is pinned (otherwise it repeats NR3-2's pattern)"; the pin covers one side. **The honest counter-argument, which I state rather than suppress:** current behaviour is correct under 60,000 adversarial cases, so this is latent regression exposure rather than present misbehaviour, and T5 is a semantically different (weaker) implementation rather than a pure fault injection — a lead could reasonably weigh this to **P3** on those grounds. **I record it as P2** because the project's own precedent (NF-2) and round 3's own stated P3 cap both point that way, and because what closing BUG-050 would assert is that the false-clean class is closed and locked, not merely currently absent. The decision on re-weighting belongs to the lead, not to me.
- **Recommended fix (two lines, no logic change):** add a third parametrize row to `test_precision_loss_fails_closed` with the excess on the **credit** side, e.g. `[Dr 1E+30, Cr 1E+30, Cr 0.01]`, which kills T7; and a fourth row at a magnitude no fixed-precision bump can absorb, or an assertion on the raised message distinguishing the trap route, which kills T5. Do not fix this inside the review — it needs its own fresh re-review.

### NR4-2 · P3 · `test_precision_boundary_within_context_still_compares_exactly` cannot distinguish the condition it is named for; mutant T6 survives, and the claim is restated as fact in two durable records

- **Where:** `backend/tests/contract/test_financial_invariant_scaffold.py:179-188`.
- **What it claims:** its own docstring — "A sum that fits exactly within the 28-digit context precision must still be compared normally, **not treated as a precision failure**."
- **What it actually asserts:** `with pytest.raises(FinancialInvariantViolation, match="DEBITS_NE_CREDITS")`. Because the remediation reuses the identical `DEBITS_NE_CREDITS` token for both the `except Inexact` re-raise and the real comparison failure (see NR4-3), that assertion passes **whichever route raised**. The test is tautological with respect to its own stated purpose.
- **Executed evidence:** mutant **T6** adds `ctx.prec = 27` alongside the trap, which converts this exact case from `VIOLATION[COMPARISON]` to `VIOLATION[PRECISION-TRAP]` — the precise outcome the test is named to prevent — and the suite still reports **17 passed (SURVIVED)**. My own `probe_precision.py` had to label the two routes by inspecting the message body to tell them apart at all.
- **Where the unverified claim is restated as fact:** `knowledge/00-System/CURRENT_HANDOFF.md:26` ("plus a boundary test confirming an exactly-28-digit sum still compares normally") and `BUG-050-financial-invariant-placeholder-false-clean.md:49` ("plus a boundary test confirming a sum that fits exactly within the 28-digit precision is still compared normally (not treated as a precision failure)"). Both state as confirmed something the test does not confirm. This is the same evidence-accuracy class NR3-3 flagged.
- **Fix:** assert on the distinguishing part of the message (e.g. `match="total debits"`), or give the precision condition its own error code per NR4-3 and assert the absence of it; then correct the two records' wording.

### NR4-3 · P3 · `DEBITS_NE_CREDITS` is reused for a condition that is not a debits-not-equal-credits violation, and genuinely balanced sets are reported as violating the invariant

- **Where:** `backend/tests/contract/test_financial_invariant_scaffold.py:72-77`.
- **What happens:** the trapped-`Inexact` path raises `FinancialInvariantViolation("DEBITS_NE_CREDITS: leg amounts could not be summed without rounding …")`. The *condition* is "the invariant could not be evaluated at this precision," which is not the same proposition as "total debits differ from total credits." For a genuinely balanced set whose legs span more than 28 significant digits — e.g. `Dr 1E+30 + Dr 0.01` vs `Cr 1E+30 + Cr 0.01`, where debits **do** exactly equal credits — the harness reports `DEBITS_NE_CREDITS`.
- **Executed evidence:** that case raises `VIOLATION[PRECISION-TRAP]` in my probe run; the unrestricted fuzz produced **14,550 of 40,000 cases** that are exactly balanced by the `Fraction` oracle yet reported as violations. All are extreme-exponent synthetic shapes; the plausible-money fuzz produced **0 of 20,000**, so there is no practical impact at this scope.
- **Why it is a finding and not just naming taste:** the direction is fail-closed, which is correct and is why this is P3 rather than higher. But (a) it is what makes NR4-2 possible — a shared token is why the boundary test cannot discriminate; (b) round 3's own recommendation was to re-raise "as a named `FinancialInvariantViolation`-family error," and a distinct code (e.g. `DEBITS_CREDITS_UNEVALUABLE_PRECISION`) is what satisfies that; and (c) this placeholder is the template the real ledger module inherits, where a consumer matching on `DEBITS_NE_CREDITS` would mis-diagnose an unevaluable posting as an out-of-balance one. SCN-133's own acceptance text requires the harness to fail "citing the specific invariant violated" — citing `DEBITS_NE_CREDITS` for a set where that invariant holds is a weaker form of that guarantee than the scenario asks for.
- **Fix:** give the precision condition its own error code in the same `FinancialInvariantViolation` family, keep the fail-closed behaviour unchanged, and update `test_precision_loss_fails_closed` to match the new code.

## Observations (no finding)

- **Empty leg list still passes vacuously.** `assert_debits_equal_credits([])` reports balanced; `sum((), start=Decimal(0))` performs no arithmetic, so no trap and `0 == 0`. The function itself has no non-empty guard — the protection is the `assert balanced, "fixture must be non-empty; an empty set passes vacuously (not a proof)"` line in `test_balanced_synthetic_entries_pass`, which is what kills M12. Rounds 2 and 3 both recorded this as acceptable at placeholder scope and I agree; I record it so it is not mistaken for unexamined. A future real ledger harness should reject an empty posting at the function boundary.
- **`localcontext()` does not leak.** After every probe, the caller's context still shows `traps[Inexact] = False`, `prec = 28`. A caller-supplied non-default context is inherited (a lower `prec` makes the harness stricter, a higher one less strict) but cannot produce a false clean, because an exact sum compares exactly in any context.
- **Superuser DSN for the scaffold probe.** `app/modules/conftest.py:33` connects as the container superuser for a `SELECT 1` liveness probe only (`current_user: postgres`, confirmed live). It makes no isolation claim, so it is acceptable here; real domain suites must use the non-privileged runtime role per `.claude/rules/backend/database.md` control 5. Unchanged from round 3.
- **Co-tenant container, carried forward, not mine and not new.** `frosty_bhabha` (`mikeh1975/tradingview-mcp:latest`, an unpinned third-party image) is still running on the CAP-008 Colima engine's default bridge and still unrecorded in CAP-008 evidence. Slice 7 adds another `disposable_postgres()` consumer on that bridge with a random per-run password, loopback-only publish and synthetic data only; nothing in Veyro treats that container as trusted or reads anything from it. Recommendation unchanged from rounds 2/3: record it in CAP-008 evidence, or isolate `disposable_postgres()` on a per-run `--internal` network through a separately governed change. **I did not touch it.**
- **Second (Docker Desktop) CLI on PATH** is a positive confirmation of the CAP-008 P1-1 pin, as round 3 recorded, not a finding: PATH's first `docker` is Docker Desktop's and the harness demonstrably refuses it.
- **No credentials, no real member data.** A credential/PII-shaped grep (`password|secret|token|api_key|ssn|passport|iban|credit_card|email-shaped`) across both Slice-7 contract files and the whole of `backend/app/modules/` returns only two hits, both the substring `ssn` inside the word `classname` in `test_domain_scaffold_inventory.py:101-102`. Tenants are `uuid4()` values; accounts are `synthetic:cash` / `synthetic:revenue` / `synthetic:deferred`; the Postgres superuser password is generated per run, kept out of argv and `repr`, and never committed. Consistent with `.claude/rules/infra/secrets.md` controls 1-3.
- **`TEST_RESULTS.md`** still carries only the round-2-era `184/184` and `14/14` figures, explicitly labelled "after round-2 remediation", with no Slice-7/SCN-132/133 promotion entry. That is dated-accurate and correct for two unpromoted scenarios; not a finding. It will need the round-4 figures (189/189, 19/19) whenever promotion happens.
- **`.claude/settings.json`** is modified in the working tree, but the diff is a single SessionStart hook-text update (MOD-000 wording to MOD-001 wording), unrelated to Slice 7 and predating it. Not Slice-7 scope; recorded so it is not read as an undisclosed capability change.
- **Python version:** venv is 3.14.5, `pyproject` requires >=3.13. Consistent.

## Model routing and capability integrity

- **Judgment routing satisfied.** Both SCN-132 (judgment half) and SCN-133 are routed to `veyro-security-reviewer`/Opus. This review is that gate, in a fresh context, with an agentId distinct from the implementer, the code reviewer and both prior security reviewers. The earlier Opus code review does not satisfy this routing, and per DC-06 no session reviews its own work.
- **Build routing.** The routine portion was built on Sonnet, consistent with DC-17 and SCN-132's dual-tier split (Sonnet mechanical run, Opus judgment). Round 3 independently re-verified the implementer transcript at 228/228 `claude-sonnet-5`; I did not re-run that attestation and make no claim about its current turn count.
- **No critical-slice misrouting.** `backend/tests/harness/tenant_isolation.py` is confirmed **untouched**: SHA-256 `3012342ee02fb42088df48e7b1607b2157569e7b2393d6641fa91c3be4a8f337`, byte-identical to round 3's recorded value; mtime `Sep 29 07:40`, before the slice; it does **not** appear in `git status --porcelain backend/tests/harness/` at all (committed and unmodified); and a grep for `tenant_isolation` across both Slice-7 contract files and all of `backend/app/modules/` returns **NONE**. The ADR-005 Decision 1 critical harness was neither modified nor duplicated.
- **No new or unregistered capability.** `backend/pyproject.toml` is unchanged (`039332c96ab93d82de930d1c84e3351a160829604126868da3a2a8fdfdd40695`, matching rounds 2 and 3; `git diff --stat` shows no delta). The complete import set across the Slice-7 surface is stdlib only (`__future__`, `collections.abc`, `dataclasses`, `decimal`, `enum`, `pathlib`, `subprocess`, `sys`, `tempfile`, `typing`, `uuid`, `xml.etree.ElementTree`) plus `psycopg`, `pytest`, and in-repo modules. No third-party capability is relied on beyond CAP-008, and nothing here was treated as trusted without qualification evidence. Per `CAPABILITY_POLICY.md`'s fail-closed rule, nothing in this slice required an unregistered capability, and `BLOCKED: CAPABILITY_UNREGISTERED` was not reached.
- **CAP-008 used strictly inside its approved scope, with no scope broadening.** Same `disposable_postgres()` entrypoint, same digest-pinned image, same pinned Colima socket and Homebrew CLI realpath, loopback-only publish, synthetic fixture data only, no Docker Desktop, container force-removed. `capability_drift_check.py` reports no drift; `validate_capabilities.py` confirms all required supply-chain fields present. The CR P2-6 registry-wording gap (the row's scope text names only the tenant-isolation/authn harness, not this second consumer of the identical binding) persists and remains accurately disclosed; it is a record-wording gap, not a grant of broader scope than need, and I do not raise it as a new finding since both prior rounds already recorded it.
- **Owner-reserved restrictions, all four re-checked rather than assumed:** (1) **no paid service or spend of any kind** — everything run is local and free (venv pytest/ruff/mypy, project-authored validators, local Colima, no registry pull beyond the already-cached pinned digest, no SaaS call); (2) **no real member data** — synthetic fixtures only, verified by the credential/PII scan above; (3) **no deploy or Production promotion** — nothing was committed, pushed, tagged, or deployed; HEAD unchanged at `e516bed…`; (4) **no material product, pricing, business, architecture, or scope change** — this review changed no code, no scenario status, no bug status, no registry entry, and no ADR. Nothing in this slice approaches an owner-reserved boundary. `BLOCKED: OWNER_APPROVAL_REQUIRED` was not reached.

## Evidence-accuracy check

**Accurate, independently matched:**
- Full suite **189/189**; focused contract tests 19/19; six direct scaffold runs 6/6.
- `ruff check` clean; `ruff format --check` clean on the two Slice-7 files specifically; repo-wide back to 7 pre-existing non-Slice-7 files; mypy strict clean, 47 source files.
- `verify_baselines.py` 4/4; `validate_capabilities.py`, `capability_drift_check.py`, `validate_repo_skeleton.py`, `validate_baseline_binding.py`, `validate_migration_ordering.py`, both `validate_capability_manifest.py` runs, `evidence_integrity_check.py` (365 files) all PASS; `run_regression.py` AGGREGATE PASS 4/4 with 1 N/A; `module-deps` `GATE_NOT_IMPLEMENTED`, never claimed PASS.
- Unscoped `git diff --check` clean.
- BUG-050's and `CURRENT_HANDOFF.md`'s claims that N1/N2/N3 now raise `DEBITS_NE_CREDITS`, that mutant M14 is now killed, and that the 40-leg accumulation and the `100.00`/`25.50` fixture are unaffected — **all four independently re-executed and confirmed**.
- BUG-050 status **OPEN** (front matter and `BUG_REGISTRY.md:206`), SCN-MOD001-132 and -133 both still `NOT EXECUTED` in `SCENARIOS.md` (lines 919, 958), `TEST_RESULTS.md` carries no promotion entry. **No self-closure or self-promotion anywhere.** Correctly maintained.
- The round-3 review's own `/tmp` disclosure practice, which I followed.

**Inaccurate, incomplete, or overstated:**
- **NR4-2:** `CURRENT_HANDOFF.md:26` and `BUG-050…md:49` both state that the new boundary test *confirms* an exactly-28-digit sum "still compares normally (not treated as a precision failure)." The test cannot confirm that — mutant T6 makes the case a precision failure and the test still passes.
- **BUG-050:49/52 and `CURRENT_HANDOFF.md:26`** describe the round-3 remediation as "closing NR3-1." The *behaviour* is closed, which I confirm with stronger evidence than the record claims. The *regression lock* is not — NR4-1. A reader could take "closing NR3-1" as covering both.
- `BUG-050`'s front matter still carries `severity: P1` while round 3's verdict was P2=1/P3=2. That is the bug's original filing severity rather than a current-round severity, consistent with how this project records bugs, so I note it without raising it as a finding.

## SHA-256 (at review time)

| File | SHA-256 |
|---|---|
| **backend/tests/contract/test_financial_invariant_scaffold.py** (round-3 remediated; was `03a32988…d583ee`) | **ee3aecdf5724d4bbe99dd341a96a2efb78f655624bbb7eab8a9b6b32e92d7b72** |
| **backend/tests/contract/test_domain_scaffold_inventory.py** (unchanged since round 3) | **ef6d23fa49a7f15198afe0a060a6bc922bc944414aac8f1f15d84fb9cafd021a** |
| backend/app/modules/conftest.py | c6ecb7bbdfa81e401a73afa12b1023598de6652fbac57d6a532a11a8017c6ca5 |
| backend/app/modules/_shared/__init__.py | b63dac5610c1a4addd3aa859ad6a0d2894b7733d80c735e6fffc20cac8d4acd0 |
| backend/app/modules/_shared/tenant_context.py | 54cd64413d8d034307809aa9d529e931b448290749941d44b2d861c40d21b815 |
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
| backend/tests/harness/postgres.py (reused, not reviewed for change) | 3e4c7d451aaa23e1bfec42a1c7d4e8774eecb72eafec0f2f35b842a4cf1f5f67 |
| backend/tests/harness/tenant_isolation.py (critical slice, confirmed UNTOUCHED) | 3012342ee02fb42088df48e7b1607b2157569e7b2393d6641fa91c3be4a8f337 |
| backend/pyproject.toml (unchanged) | 039332c96ab93d82de930d1c84e3351a160829604126868da3a2a8fdfdd40695 |
| GOV01-R02-SLICE7-…-SECURITY-REVIEW-2026-10-03.md (round 2) | 6a6a0b8c2034fbcc5e95d8e0f02799e07d654ce36a007f5a6003c08449474629 |
| GOV01-R02-SLICE7-…-SECURITY-REVIEW-ROUND3-2026-10-03.md (round 3) | 0781aea6cc89a52ac615d3045e2cd1c922bbefb6a677a6010f1cfe27718f5521 |
| BUG-050-financial-invariant-placeholder-false-clean.md | fb71db2af30886ef7483ec2e8a49c2dbbf19929771ebc5a1fcc2df72ce6e2957 |
| /tmp/r4-tools/probe_precision.py | 341f0ac0401291248c79d87f8d7c1665a7e0242cd8466d301b5d3a7b1192cabb |
| /tmp/r4-tools/mut.py | f6c85e3c6e62c8e49ea0777a7d8f8f0bbc0696f5c19565816b590cebc9aa08e4 |
| /tmp/r4-tools/survivor_probe.py | f2a7eb955c10e5f0f5d2f318da706942f20b72e948d456f7c4d3f5bdde610080 |
| /tmp/r4-tools/cases.py | fed5f1cdcc6bc6f580b8967922063446fa22d55622f341ca3696213a8fc843e6 |
| /tmp/r4-tools/sumblock.txt | 385f8261956a3c79f765a0646c091f783b608a255133c663526320bd08e6aa95 |
| /tmp/r4-tools/equiv.py | 21b0a4ee936cae4bf779e252de73246e6dcb80cc3e0ae3ef8a6c052c68e01ad0 |
| /tmp/r4-tools/drill_inv.sh | a7aeffe3ee678b456f045d90319dcb575090a42af29f9f2d246b4ec5e47e39b4 |
| /tmp/r4-tools/verify_live.py | 86f965d08c65f78bb64e5741b707b516ebdc1a161b6d7a5816a6f56e6d31d9c5 |
| /tmp/r4-tools/fuzz_oracle.py | 3a44b650e430ea306d02aa9b9635f44111207690c105a47ba90fffc359f44c58 |
| /tmp/r4-tools/fuzz_money.py | 3296a81d82e9e53f0e7f3d57ec8c8c61d438b4e69cc593e3fa1007f75a2d8a49 |
| /tmp/r4-tools/RUN_20261003T134417Z.txt (kept copy of the regression artifact I removed) | 8e433de2dad21dded27b39a6f15c10ecc6872c26f8e457aeef3d79bac3e679f4 |
| /tmp/r4-tools/RUN_20261003T135502Z.txt (kept copy of the second regression artifact I removed) | a673c5d473b3bd4989636e7b0a8250a7c659ca3dced49de17243af9218a1097d |

## Working-tree preservation

`git status --porcelain` before any work: 191 entries. At closeout: **identical, `diff` empty**. HEAD unchanged at `e516bedabf3d654ad3ae16d948b8f3522739ddc2`.

- `ruff` ran with `--no-cache`; `mypy`'s cache went to `/tmp/r4-mypy`; `pytest` ran with `-p no:cacheprovider`; probes imported with `-B`.
- All mutations, drills and probes ran only under `/tmp/r4-drill` and `/tmp/r4-tools`; every inventory drill restored the copy from the real tree and re-verified it green (A0 and A1 both 2 passed).
- `/tmp/r4-drill` — the throwaway `rsync` backend copy and every mutated module file — was **deleted at closeout**; `/tmp/r4-tools` retains only the hashed probe scripts and the one kept regression artifact.
- The one repo file the tooling created (`RUN_20261003T134417Z.txt`, inside `run_regression.py`'s own `regression-runs/` output directory) was removed by me and kept in `/tmp`; a before/after listing confirms that directory is byte-identical to baseline. Its in-repo path is deliberately not spelled out here — see the Disclosure note above.
- The `frosty_bhabha` container was not touched; no harness container was left behind (`docker ps` confirms).
- No scenario, bug, registry, capability or ADR status was changed; nothing was committed, pushed, reset or stashed.

The only intended working-tree delta from this review is this report file itself.

## Verdict and eligibility

**BLOCKED.** P0=0, P1=0, **P2=1 (NR4-1)**, P3=2 (NR4-2, NR4-3).

Per `DEVELOPMENT_CONSTITUTION.md`'s zero-known-defects rule (no certification while any P0/P1/P2 defect exists) and DC-12 (a passing test is not itself sufficient grounds for approval):

- **(a) BUG-050 closure: NOT eligible.** The round-3 fix is behaviourally real and now confirmed by far stronger evidence than any prior round — zero false cleans across 60,000 differential-fuzz cases and 20 of 25 mutants killed, including every mutant that removes, narrows or swallows the trap. But NR4-1 leaves half the guard unpinned, and two surviving mutants each reproduce the BUG-050 false-clean class. Closing the bug would assert the class is closed and locked; the evidence supports "closed" and not yet "locked." The remaining work is two parametrize rows.
- **(b) SCN-MOD001-133 promotion: NOT eligible**, pending NR4-1, and ideally NR4-2/NR4-3, which touch the same function and the same records.
- **(c) SCN-MOD001-132 promotion: no blocking finding of its own.** Its positive case and both literal negative forms pass; all 14 inventory drills — including round 3's e1/e2 and e3/e4 — reproduce exactly; the file is byte-identical to the version round 3 cleared; NF-3/NF-5 remain fixed and order-independent; NF-7 remains a disclosed, accepted P3 limitation. All three round-4 findings are in the SCN-133 file. **Whether to promote SCN-132 separately is the orchestrator's or lead's call, not mine** — I record only that I found nothing blocking it, and note it would be promoted while sharing a bug (BUG-050) that stays open for the SCN-133 half.

**Recommended minimal remediation** (all three are small; I tested none of them in the real tree and applied none):
1. **NR4-1** — add a credit-side precision row to `test_precision_loss_fails_closed` (e.g. `[Dr 1E+30, Cr 1E+30, Cr 0.01]`) to kill T7, plus a row or message assertion that a fixed-precision bump cannot absorb, to kill T5.
2. **NR4-2** — make the boundary test assert on the distinguishing part of the message (or on the absence of the precision code), and correct `CURRENT_HANDOFF.md:26` and `BUG-050…md:49`, which state its claim as confirmed.
3. **NR4-3** — give the unevaluable-precision condition its own error code in the `FinancialInvariantViolation` family, keeping fail-closed behaviour unchanged.

Each fix then needs a fresh independent `veyro-security-reviewer`/Opus re-review that re-runs this drill set (a-i, e1-e4), the full mutant set (M1-M15 **plus T1-T9**), the N-series precision probes, and ideally the differential fuzz.

**Out of scope and untouched:** R04, ADR-010 Amendment A2, SCN-067 and the Anthropic model-assurance safeguard remain separately BLOCKED. I did not retry that request, route around it, or evaluate it in any way.

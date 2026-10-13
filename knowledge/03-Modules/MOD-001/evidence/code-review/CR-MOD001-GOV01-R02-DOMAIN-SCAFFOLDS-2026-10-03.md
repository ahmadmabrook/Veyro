---
doc: CR-MOD001-GOV01-R02-DOMAIN-SCAFFOLDS-2026-10-03
module: MOD-001
requirement: GOV-01-R02 (routine, non-critical-slice portion)
scenarios: SCN-MOD001-132, SCN-MOD001-133
reviewer: veyro-code-reviewer (fresh context, no memory of implementation)
model_assurance: Orchestrator post-review `mr_verify.py` PASS: 35/35 turns `claude-opus-5-5`, role veyro-code-reviewer; exact transcript below. The original reviewer self-report caveat was false and is superseded.
date: 2026-10-03
verdict: BLOCKED
counts: P0=0, P1=1, P2=6
---

# Code review — GOV-01-R02 domain scaffolds + financial-invariant scaffold

## Verdict: BLOCKED (P0=0, P1=1, P2=6)

The domain-scaffold half (SCN-MOD001-132) is sound and its fail-closed
mechanism was independently proven. The financial-invariant half
(SCN-MOD001-133) carries one P1: the harness does not compute
debits vs credits at all, so it both rejects a correct double-entry posting
and accepts a set with no credit legs. That defeats SCN-133's stated
purpose ("proving the harness itself detects a real violation, not a
rubber-stamp pass").

## Scope reviewed (untracked files, `git status --porcelain=v1 -- backend/app/modules backend/tests/contract`)

`backend/app/modules/_shared/tenant_context.py`, `backend/app/modules/conftest.py`,
`backend/app/modules/{membership,booking,payment,ledger,pos,access}/__init__.py`,
`.../tests/__init__.py`, `.../tests/test_scaffold_live.py`,
`backend/tests/contract/test_domain_scaffold_inventory.py`,
`backend/tests/contract/test_financial_invariant_scaffold.py`.
(`app/modules/__init__.py` and `_shared/__init__.py` are pre-existing, committed in `cd3723c`.)

Out of scope, noted only: the working tree also has unrelated uncommitted
work (`tests/harness/postgres.py`, `authn.py`, `migration_safety.py`,
`test_architecture_gate_rls.py`, `test_migration_safety_harness.py`,
`migrations/rls-manifest.json`). The dispatch claim "nothing else in the
repo was modified" is true only of this change set, not of the working tree.

## Evidence checked (all run by this reviewer, 2026-10-03)

| Check | Result |
|---|---|
| `cd backend && .venv/bin/pytest -q` | 174 passed, exit 0 |
| `.venv/bin/ruff check .` | All checks passed |
| `.venv/bin/mypy app tests` | Success, 46 source files |
| `pytest -v app/modules` (direct) | 6/6 domain `test_scaffold_live` PASSED |
| `pytest -v` on both new contract files | 4/4 PASSED |
| `pyproject.toml` `testpaths = ["tests"]` | domain scaffolds are not double-collected; they run only via the inventory subprocess (or explicitly) |
| `ruff format --check` on new files | 2 new contract files not formatter-clean (P2-4) |

### Independent fail-closed drill (SCN-132 negative case)

Throwaway copy at `/tmp/veyro-cr-drill-hSRx/w` (`app/`, `tests/__init__.py`,
`tests/harness/`, `tests/contract/`, `pyproject.toml`), running
`test_domain_scaffold_inventory.py` with the repo venv. Copy deleted after;
verified no `/tmp/veyro-cr-drill-*` remains and the repo's change set unchanged.

| Variant | Result |
|---|---|
| A. unmodified copy | 2 passed, exit 0 |
| B. ledger assertion changed to `assert False` | exit 1; `inventory not clean (exit=1): {'ledger': 'failed'}` |
| C. booking `test_scaffold_live.py` deleted | exit 1; `missing domain scaffold(s): ['booking']` (second test also fails, listing all six NOT_COLLECTED, see P2-3) |
| D. pos test function renamed (0 tests collected, inner pytest exit 0, "5 passed") | exit 1; `inventory not clean (exit=0): {'pos': 'NOT_COLLECTED'}` |
| E. access test marked `@pytest.mark.skip` (inner "5 passed, 1 skipped") | exit 1; `{'access': 'skipped'}` |

Variants D and E are the important ones: the inner run reports green with
five domains, and the inventory still fails closed and names the domain.
This is exactly the "never silently green with five collected" requirement.

## Findings

### P1-1 — Financial-invariant harness does not check debits == credits (SCN-MOD001-133)

`backend/tests/contract/test_financial_invariant_scaffold.py:33-40`:

```python
total = sum((entry.amount for entry in entries), start=Decimal(0))
if total != Decimal(0):
    raise FinancialInvariantViolation(f"DEBITS_NE_CREDITS: ...")
```

Each `SyntheticLedgerEntry` already has both a `debit_account` and a
`credit_account`, but the check ignores both and only requires that signed
amounts net to zero. That is not the double-entry invariant. I ran three probes
against the shipped function:

| Synthetic set | Correct double-entry outcome | Harness outcome |
|---|---|---|
| One posting: Dr cash / Cr revenue 100 | balanced | **VIOLATION** (`net balance 100 != 0`) — false positive |
| Two legs with `credit_account=""` (+10, −10), i.e. debits with no credit leg | unbalanced | **PASS** — false negative |
| Shipped "balanced" set (Dr cash/Cr revenue 100 + Dr revenue/Cr cash −100) | the second row is the same economic posting as the first (swapped sides and negated amount), not its reversal | PASS only because the signed amounts cancel |

The negative fixture (`test_unbalanced_synthetic_entry_fails_closed`) adds a
row that *has* a matching credit leg. So it is not the "debit with no matching
credit" SCN-133 names. It fails only because of the net-sum artifact. The
`DEBITS_NE_CREDITS` label is attached to an invariant that the code does not
actually evaluate. As written, the scaffold would also model the wrong
invariant for the future ledger module that inherits it.

Required fix (mechanical, still placeholder-only): model legs explicitly,
e.g. `(entry_id, account, side ∈ {DEBIT, CREDIT}, amount > 0)`, and assert
Σ debit amounts == Σ credit amounts (per entry_id and/or across the set). The
negative fixture should be a DEBIT leg with no CREDIT leg. Optionally, add the
two probes above as regression cases.

### P2-1 — Test-only `StaticTenantContextResolver` lives in the production package

`backend/app/modules/_shared/tenant_context.py:43-56`. Its docstring says it is
test-only and must never be wired into a request path, but it ships under
`app/` and accepts an arbitrary caller-supplied tenant. That is the
footgun `database.md` control 4 / `TEN-002` warns against. The `TenantContext`
and `TenantContextResolver` protocol belong in `_shared/` (architecture.md
control 3 names "the tenant-context resolver" explicitly), but the static
implementation should move to test code (e.g. `app/modules/conftest.py` or
`tests/harness/`). No security claim is overstated: the module docstring
explicitly disclaims authentication, and nothing outside the six scaffolds
imports it today. P2, not P1, because no request path exists yet.

### P2-2 — Domain scaffolds import `Conn` from the critical-slice harness module

All six `test_scaffold_live.py` import `Conn` from `tests.harness.tenant_isolation`
(the ADR-005 Decision 1 `veyro-critical-engineer` harness), although
`app/modules/conftest.py:22` defines an identical alias. The import is only a
type alias: `tenant_isolation.py` has no import-time side effects, it is
unmodified, and no RLS/auth logic is duplicated or altered. Still, it is an
avoidable routine→critical-module coupling. A future change to that harness's
module would ripple into six routine files. Use the conftest/local alias instead.

### P2-3 — Deleted-scaffold case produces a noisy second failure

When a domain file is deleted, inner pytest exits 4 before writing junit, so
`test_all_six_domain_scaffolds_pass` reports all six domains as
`NOT_COLLECTED`. The companion `test_all_six_domain_scaffold_paths_exist`
names the correct domain, so the scenario is still satisfied. Passing only
existing paths (or skipping the subprocess when paths are missing) would make
the second message precise.

### P2-4 — New contract files are not `ruff format`-clean

`test_domain_scaffold_inventory.py` and `test_financial_invariant_scaffold.py`
fail `ruff format --check` (e.g. the hand-wrapped list at
`test_financial_invariant_scaffold.py:60-62`). No gate I found enforces
formatting (`ruff check` passes; no `.github/workflows` present), so this is
non-blocking.

### P2-5 — Change set depends on uncommitted CAP-008 harness changes

The scaffolds run through `disposable_postgres()`. HEAD's
`tests/harness/postgres.py` contains no Colima binding (`grep -ci colima` = 0).
The approved CAP-008 Colima pinning exists only as an uncommitted modification.
If this change set were committed alone, it would sit on the HEAD harness, which is the
Docker Desktop-era unqualified binding (BUG-038 history). Commit it with or
after the CAP-008 harness changes.

### P2-6 — CAP-008 registry scope text names only the tenant-isolation/authn harness

`CAPABILITY_REGISTRY.md` CAP-008 row says the capability is "used by
`backend/tests/harness/postgres.py` for the MOD-001 GOV-01-R02
tenant-isolation/authn harness." This change adds a new consumer
(`app/modules/conftest.py`, the GOV-01-R02 domain scaffolds) through the same
entrypoint, with the same loopback/synthetic scope. I judge this within the
approved binding, not an unregistered capability use. It is not a
`BLOCKED: CAPABILITY_UNREGISTERED` condition. The registry's usage text should
still be widened at the next registry touch.

### Observation (not a finding)

`IMPLEMENTATION.md` §3's financial-invariant row lists "Fixture DB +
RLS-enabled schema" as its environment, "once a domain exists." SCN-133's own
steps require only a synthetic row set, and no domain exists yet, so the
in-memory scaffold is acceptable at this stage. Once the ledger domain lands,
this should migrate to the fixture DB under the runtime role.

## Rule / baseline conformance

- architecture.md control 5 (empty-scaffold carve-out): conforms. The domain
  `__init__.py` files are docstring-only, and the tests assert no product
  behavior. No cross-domain imports.
- architecture.md control 3 (`_shared/` domain-free): conforms for the
  contract types. See P2-1 for the test double.
- database.md: no tenant tables, migrations, roles, or RLS policies are
  touched. Scaffold connects as container superuser only for `SELECT 1`, which
  is not an isolation assertion, so control 5 is not engaged. Nothing was missed.
- ADR-005 Decision 1 routing: no duplication or modification of
  `tenant_isolation.py`/`authn.py` logic. Only `disposable_postgres()` is
  reused, plus the type alias in P2-2.
- Owner-reserved restrictions: no spend, no real member data (uuid4 /
  `synthetic:*` only), no deploy, no material scope change. No secrets: the
  DSN comes from the disposable container at runtime.
- Capability use: CAP-008 (APPROVED), see P2-6. No new tool or dependency.

## Scenario promotability

- **SCN-MOD001-132**: the positive case (6/6 pass) and negative case (drill
  B/C/D/E) are evidenced. On the deliberate-violation question, I agree with
  proving the negative case in a throwaway copy instead of committing a
  permanently broken fixture. A committed broken domain scaffold would keep
  the inventory permanently red, or force an exclusion mechanism that is itself a
  silent-green risk. Round 11's correction asked for a real deliberate
  violation in place of a "check does nothing" assertion. Variants B–E are
  real violations that produce non-zero, domain-named failures. They are also
  consistent with round 11 rejecting `--gate module-deps`: this is a
  test-level check, not an architecture gate. Still, a repeatable drill
  script committed under `evidence/` would make this durable (non-blocking
  suggestion). **Not promotable on this review alone**: SCN-132 is routed
  `veyro-security-reviewer/Opus (judgment)` + `veyro-implementer/Sonnet
  (mechanical run)`. This code review is neither of those roles.
- **SCN-MOD001-133**: **not promotable.** P1-1 must be fixed first.
  Separately, SCN-133 is routed solely to `veyro-security-reviewer/Opus`, so
  even a clean code review cannot satisfy its routing. A distinct security
  review is required after the fix.

No scenario-promotion field, CURRENT_STATE, CURRENT_HANDOFF, or
BUG_REGISTRY was edited by this reviewer. Reconciliation (including whether
P1-1 is filed as a BUG-NNN) is left to the orchestrating session.

## Orchestrator model-assurance correction (2026-10-03)

The reviewer incorrectly said no Claude Code JSONL existed. The ACPX-launched Claude project did create `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/1bba8cd1-c383-477f-8d41-195fb71de236/subagents/agent-a4018a8a551393f5c.jsonl`; the matching `.meta.json` names `veyro-code-reviewer`. The orchestrator independently ran `backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <transcript> opus veyro-code-reviewer`: PASS, 35/35 turns on `claude-opus-5-5`, no fallback. This does not change the BLOCKED P1/P2 verdict on the pre-fix version.

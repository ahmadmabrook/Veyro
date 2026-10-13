# SCN-MOD001-070 — Round-1 Remediation (R1-1 … R1-6)

Date: 2026-10-04 (session start 12:05Z, closeout 12:13Z)
Scope: SCN-MOD001-070 / GOV-01-R06 migration-ordering lint **only**.
Status: **REMEDIATED, NOT REVIEWED, NOT PROMOTED.** This is an
implementation-tier record. It is not a self-approval, not an independent
review, and does not promote SCN-MOD001-070 or certify MOD-001.

Round-1 report under remediation:
`../security/SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND1-2026-10-04.md`
(verdict BLOCKED, P0=0 / P1=1 / P2=5 / P3=5).

---

## 1. Runtime model/session evidence (MODEL_ROUTING no-silent-downgrade rule)

`MODEL_ROUTING.md`'s no-silent-downgrade rule requires **both** a
configured family alias **and** runtime evidence (resolved model identity
plus session id); the `model:` declaration alone is insufficient.

- Session id (`CLAUDE_CODE_SESSION_ID`): `fc84a793-79c0-4a6f-b491-b061ea27746f`
- `CLAUDE_CODE_CHILD_SESSION=1`, `AI_AGENT=claude-code_2-1-274_agent`,
  `CLAUDE_AGENT_SDK_VERSION=0.3.274`, `CLAUDE_EFFORT=high`,
  `CLAUDE_CODE_ENTRYPOINT=sdk-ts`, `CLAUDE_PID=31229`
- Transcript: `~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/fc84a793-79c0-4a6f-b491-b061ea27746f.jsonl`

Verified with this project's own tool, not by self-attestation (per
`mr_verify.py`'s documented finding that no environment variable exposes
the resolved model — the transcript `model` field is the real signal):

```
$ backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py \
    ~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/fc84a793-79c0-4a6f-b491-b061ea27746f.jsonl \
    opus scn070-remediation-implementation-session
{
  "verdict": "PASS",
  "reason": "24 turn(s), 100% consistent, model 'claude-opus-5' matches required tier 'opus'.",
  "models_observed": [
    "claude-opus-5"
  ],
  "expected_tier": "opus"
}
EXIT=0
```

`claude-opus-5` is an exact member of `mr_verify.py`'s DC-17-qualified
Opus allowlist (`_QUALIFIED_MODELS["opus"]`), not a shape match. No
mid-task substitution across 24 assistant turns. The label used is
deliberately a distinct, accurate description of this session rather than
a registered role name — `mr_verify.py` blocks near-miss labels, and
claiming a registered agent's name for a session that is not that spawned
agent would be a false attestation. Re-running the command above later
will report a higher turn count (the transcript grows); the invariant to
check is the single `claude-opus-5` value, not the count.

### Routing deviation, stated rather than silently taken

The dispatching brief asked for the **Opus-qualified `veyro-critical-engineer`
role**. That agent's registered scope is bounded, by
`ADR-005` Decision 1 and its own frontmatter, to exactly three MOD-001
slices: the tenant-isolation/RLS harness and its fixture schema, the
authentication negative-credential fixture pattern (both GOV-01-R02), and
TSD §24.1's RLS-lint + permission-lint architecture gates (GOV-01-R04).
**The GOV-01-R06 migration-ordering lint is none of those three.** Both
`MODEL_ROUTING.md`'s critical-slice row and the agent definition itself
state that extending the role to a new slice requires its own ADR
amendment per DC-17's routing-change sub-clause — "do not silently broaden
scope."

So the Opus *tier* requirement was honored and runtime-verified above,
while the critical-engineer *role* was deliberately **not** invoked, since
doing so would have been exactly the silent scope broadening DC-17
forbids. This work's correct standing route is implementation-tier
(`veyro-implementer` / `veyro-test-author`, Sonnet) for a `tools/**` static
validator; executing it on a runtime-verified Opus session is an
over-tier, not a downgrade, so it creates no assurance gap in either
direction. **Unresolved governance item for the orchestrator/owner:** if
future GOV-01-R06 lint work is intended to be critical-engineer work, that
needs an ADR-005 amendment first — it is not something this session may
decide. Recorded, not assumed away.

---

## 2. Findings remediated

| Finding | Severity | Status | Where |
|---|---|---|---|
| R1-1 start-phase guard uncovered; mutant M3 survives | **P1** | **FIXED — M3 now KILLED** | `tools/tests/test_validate_migration_ordering.py` — `test_lone_contract_with_no_predecessors_fails_closed`, `test_lone_switch_with_no_predecessors_fails_closed` |
| R1-2 `main()` exit-code contract uncovered; mutant M5 survives | P2 | **FIXED — M5 now KILLED** | same file — `test_cli_exit_code_is_1_on_violation`, `test_cli_exit_code_is_0_on_ordered_control` (real `subprocess`) |
| R1-3 non-`.yaml`/nested records silently ignored | P2 | **FIXED (closed, not accepted-risk)** | `tools/validate_migration_ordering.py` `discover_records()`; the `*_is_not_silently_ignored` tests plus `test_gitkeep_placeholder_is_ignored_without_a_problem` |
| R1-4 typo'd `--records-dir` exits 0 with PASS line | P2 | **FIXED** | same tool: `--require-dir` + grep-able vacuous-pass NOTICE; the `*_require_dir*` / `*_vacuous_pass_notice*` tests |
| R1-5 lint invoked by no automated gate | P2 | **FIXED (local aggregator); CI carried forward** | `knowledge/05-QA/tools/run_regression.py` |
| R1-6 evidence record not re-runnable, uncovered paths undisclosed | P2 | **FIXED** | amendment appended to `SCN070-MIGRATION-ORDERING-EXECUTION-2026-10-04.md` |
| R1-7 backward-jump diagnostic misnames cause | P3 | **NOT DONE — out of this pass's bounds** | see §6 |
| R1-8 duplicate front-matter keys last-win | P3 | **NOT DONE — out of this pass's bounds** | see §6 |
| R1-9 hand-maintained test list / hardcoded count | P3 | **FIXED (load-bearing dependency of R1-1/R1-2)** | dynamic `test_*` discovery in `__main__` |
| R1-10 `migrate` record not checked for real backfill/throttling | P3 | **NOT DONE — reviewer scoped it out of SCN-070** | see §6 |
| R1-11 companions share no instrument | P3 | **No fix required (disclosure)** | — |

R1-9 was not optional despite being P3: the previous `__main__` block
hand-listed six calls and printed a hardcoded "all 6 tests passed," so
every test added for R1-1 and R1-2 would have been **silently skipped**
under the exact documented no-pytest invocation path the evidence record
used. Fixing R1-1/R1-2 without R1-9 would have produced a false green.

---

## 3. What changed, file by file

**`tools/validate_migration_ordering.py`** (SHA-256
`17f6d8457d86d794750de62db368051f7abf6aab1d2f6d93285a3f479a1f80af`)

- New `discover_records(records_dir) -> (record_paths, problems)`: walks
  the whole tree once; a record is a `*.yaml` **directly inside** the
  records dir, and every other file becomes an `UNRECOGNIZED_RECORD_FILE`
  problem naming its path relative to the records dir. Enumerate-and-reject
  was chosen over widening the glob to `("*.yaml","*.yml")` + `rglob`
  because it is explicit: a misplaced or misspelled file becomes a visible
  failure rather than an invisible omission, which is the contract the
  tool's own docstring already claimed ("never a silent partial pass").
- `IGNORED_NON_RECORD_FILES = {".gitkeep", ".DS_Store"}` — a tight
  allowlist, not a pattern. `.gitkeep` is the repo's real placeholder in
  `backend/migrations/records/`; `.DS_Store` is macOS metadata nobody
  authors. Neither is a plausible migration-record filename, so the
  exemption opens no path for a real record to hide. **Honest limitation:**
  a file literally named `.gitkeep` or `.DS_Store` containing record-shaped
  content would be skipped. That is the deliberate trade against failing
  the repo's own default run on Finder metadata.
- `validate_directory(records_dir, require_dir=False)` — the new parameter
  defaults to the previous behavior, so the signature stays
  backward-compatible and `test_empty_directory_passes` is unchanged.
  Missing dir + `require_dir` → `MISSING_RECORDS_DIR`.
- `main()`: new `--require-dir` flag; two distinct grep-able notices
  (`NOTICE: records dir does not exist — vacuous pass` /
  `NOTICE: records dir exists but contains no migration records — vacuous
  pass`) printed **only on the pass path**.

A defect introduced and then fixed within this same pass, recorded rather
than quietly corrected: the notices were first printed before the
problems block, so a BLOCKED `UNRECOGNIZED_RECORD_FILE` run printed
"vacuous pass" directly above "BLOCKED" — self-contradictory, and the same
misleading-diagnostic failure mode R1-7 describes. Moved to the pass path
and locked down by
`test_cli_blocked_run_emits_no_vacuous_pass_notice`, so the regression
cannot recur silently.

**`tools/tests/test_validate_migration_ordering.py`** (SHA-256
`49797b5ba0a75a8aa9e70e700776cf2c9063402d392c82831d0a6bf91b8e51af`)

6 tests → 18. The original 6 are byte-unchanged (behavior preserved
first). New: lone-`contract` and lone-`switch` no-predecessor cases
(R1-1); two real-`subprocess` CLI exit-code tests asserting `returncode`
**and** stdout content (R1-2); `.yml`, `.md`, nested-subdirectory, and
`.gitkeep`-still-ignored cases (R1-3); `--require-dir` unit + CLI cases,
the vacuous-pass NOTICE, and the no-NOTICE-on-BLOCKED self-check (R1-4).
`__main__` now discovers `test_*` callables from `globals()` and prints the
discovered count, and exits 1 if it discovers none (R1-9).

**`knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py`**
(new; SHA-256
`8fc9daac892307a15295a58f30e0e44cb9034d61049487364a52aea4aa5f88de`)

Reproducible replacement for the reviewer's ad-hoc `/tmp` probes, so round
2 can re-derive the verdict with one command instead of reconstructing
mutations by hand. Deliberately the same shape and safety discipline as
this module's existing `r04_gate_mutation_killcheck.py` (reuse, not a new
convention): mutants applied only to a copy inside a `tempfile` mirror;
the real tool and test file are read-only and their SHA-256s are asserted
unchanged in `finally`, at interpreter exit, and on SIGINT/SIGTERM; every
mutation anchor must match exactly once or the run aborts with exit 2
rather than reporting a kill it did not perform; an unmutated `m0`
baseline must be sane or the run aborts.

**`knowledge/05-QA/tools/run_regression.py`** (SHA-256
`22581aebd4a4b7e50615ca6e6c27ddab9049ce315682eeb156ec2c2f01aef21e`) — R1-5.
Two checks registered: the lint itself, and its unit suite. The unit suite
is the genuinely load-bearing half today, because the lint over the real
`records/` is vacuous (only `.gitkeep`); the suite is what kills M3 and M5.

**`backend/migrations/TEMPLATE.md`** — authoring guidance for
`UNRECOGNIZED_RECORD_FILE`, `--require-dir`, and the vacuous-pass notice.
R1-3 named this template as a live authoring-error path, since `.md` is
the extension authors copy from.

---

## 4. Executed results — real commands, real output

Every command run from `/Users/ahmadmabrouk/Desktop/Veyro` with
`backend/.venv/bin/python` (Python 3.14.5).

| # | Command | Result |
|---|---|---|
| A1 | `tools/tests/test_validate_migration_ordering.py` | `PASS — all 18 tests passed (discovered dynamically, not hand-listed).` exit **0** |
| A2 | `tools/validate_migration_ordering.py` (real tree, no args) | exit **0**, now also prints `NOTICE: records dir exists but contains no migration records — vacuous pass, no record was checked.` — probe T4's vacuity is now visible in the output instead of inferred |
| A3 | `tools/validate_migration_ordering.py --records-dir /tmp/scn070_r1fix/negative` | exit **1**, `0003_contract.yaml: OUT_OF_ORDER_PHASE — ... jumps to 'contract' without a preceding 'switch'` |
| A4 | `... --records-dir /tmp/scn070_r1fix/ordered` | exit **0**, PASS line, **no** NOTICE |
| A5 | `... --records-dir /tmp/scn070_r1fix/lone_contract` | exit **1**, `0001_contract.yaml: OUT_OF_ORDER_PHASE — ... starts at 'contract' but must start with 'expand'` (the R1-1 path, previously uncontrolled) |
| A6 | `... --records-dir /tmp/scn070_r1fix/yml_variant` | exit **1**, 2× `UNRECOGNIZED_RECORD_FILE` naming `0001_expand.yml` / `0002_contract.yml` (was exit 0 + PASS at round 1) |
| A7 | `... --records-dir /tmp/scn070_r1fix/nested` | exit **1**, 2× `UNRECOGNIZED_RECORD_FILE` naming `2026q4/0001_expand.yaml` / `2026q4/0002_contract.yaml` (was exit 0 + PASS) |
| A8 | `... --records-dir /tmp/scn070_r1fix/typo_nonexistent` | exit **0**, `NOTICE: records dir does not exist — vacuous pass ...` then PASS — distinguishable from a real pass, which it was not at round 1 |
| A9 | `... --records-dir /tmp/scn070_r1fix/typo_nonexistent --require-dir` | exit **1**, `MISSING_RECORDS_DIR — --require-dir was set but this directory does not exist ...` |
| A10 | `knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py` | `8/8 mutations killed; survivors=[]`, exit **0** |
| A11 | `knowledge/05-QA/tools/run_regression.py` | aggregate **FAIL (5/6, 1 N/A)** — see the honest note below |
| A12 | `knowledge/05-QA/tools/mr_verify.py` (own transcript, `opus`) | `PASS`, `claude-opus-5`, exit **0** |

Verbatim stdout for A3/A4/A5 and the fixture contents are embedded in the
R1-6 amendment to `SCN070-MIGRATION-ORDERING-EXECUTION-2026-10-04.md`.

Collateral-breakage sweep on the adjacent validators this change sits
beside, all run after the edits: `tools/validate_repo_skeleton.py` →
`PASS — all 7 required paths present.` exit 0;
`knowledge/05-QA/tools/capability_drift_check.py` →
`RESULT: PASS — 8 capabilities checked, no drift detected.` exit 0;
`knowledge/00-System/verify_baselines.py` → `PASS — all 4 governing
baseline hashes match` exit 0. (`tools/validate_capability_manifest.py`
exits 2 with an argparse usage error when run with no `--manifest`; that
is its documented interface, not a failure, and it is unrelated to this
work — it was already modified in the working tree before this session.)

### A11 — the aggregate regression result, stated honestly

`run_regression.py` reports **AGGREGATE RESULT: FAIL (5/6 checks passed, 1
N/A excluded)**. The single FAIL is **pre-existing and unrelated** to this
work:

```
[FAIL] evidence_integrity_check.py:   - STALE: knowledge/00-System/CURRENT_HANDOFF.md last committed
2026-09-29 (updated: field says 2026-10-01), but tracked module evidence (all MOD-*/evidence trees)
has a later commit dated 2026-10-04 ...
```

Proof it predates this change: the immediately prior run record,
`knowledge/05-QA/tools/regression-runs/RUN_20261004T114858Z.txt` (11:48:58Z,
before this session started), shows the identical FAIL line and
`AGGREGATE RESULT: FAIL (3/4 checks passed, 1 N/A excluded)`. This session
took it from 3/4 to 5/6 by adding two passing checks; it did not introduce
the failure and cannot clear it, because clearing it requires a **commit**
of `CURRENT_HANDOFF.md`, which this session is forbidden to make. This
run's own record is `RUN_20261004T121046Z.txt`.

---

## 5. Mutation evidence — M3 and M5 proven killed

Reproduce with:
`backend/.venv/bin/python knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py`

Kill signals: `unit` = mirror unit suite exits non-zero; `cli-negative` =
CLI over the recorded `expand+migrate+contract` fixture stops exiting 1;
`cli-lone` = CLI over the lone-`contract` fixture stops exiting 1.

```
m0 baseline (unmutated): SANE — unit exit 0, PASS — all 18 tests passed (discovered dynamically, not hand-listed).
M1 check_ordering returns [] immediately: KILLED by unit+cli-negative+cli-lone
M2 ordering predicate accepts any skip-ahead: KILLED by unit+cli-negative
M3 start-phase guard neutralized (R1-1, SURVIVED at round 1): KILLED by unit+cli-lone
M4 validate_fields returns [] immediately: KILLED by unit
M5 main() rejection exit code neutralized (R1-2, SURVIVED at round 1): KILLED by unit+cli-negative+cli-lone
M6 discovery narrowed back to glob('*.yaml') (R1-3 fix removed): KILLED by unit
M7 UNRECOGNIZED_RECORD_FILE suppressed (R1-3 fix removed): KILLED by unit
M8 --require-dir neutralized (R1-4 fix removed): KILLED by unit

real tool sha256 unchanged:  17f6d8457d86d794750de62db368051f7abf6aab1d2f6d93285a3f479a1f80af
real test sha256 unchanged:  49797b5ba0a75a8aa9e70e700776cf2c9063402d392c82831d0a6bf91b8e51af
8/8 mutations killed; survivors=[]
round-1 survivors now killed: ['M3 start-phase guard neutralized (R1-1, SURVIVED at round 1)', 'M5 main() rejection exit code neutralized (R1-2, SURVIVED at round 1)']
```

M3 is the exact mutation the round-1 reviewer *and* the orchestrator each
reproduced independently (`if phase_index != 0:` → `if False:` **plus**
`highest_index[change_id] = 0` → `= phase_index`). It is now killed by two
independent controls — the unit suite and the lone-`contract` CLI control.
M5 (`main()`'s `return 1` → `return 0`) is killed by all three. M6-M8 are
new mutants added specifically to prove the R1-3 and R1-4 fixes are
themselves load-bearing rather than untested additions.

**What this does and does not prove.** It proves each listed mutation is
detected by at least one durable control. It does not prove the lint is
free of defects outside this mutant set, and a mutation score is not a
scenario PASS. R1-7's and R1-8's fail-open paths (§6) remain unmutated and
unfixed by design.

---

## 6. Unresolved / deliberately not done

1. **R1-7 (P3) — backward-jump diagnostic misnames the cause.** Four
   ordered phases then a fifth `expand` fails closed (safe) but reports
   "jumps to 'expand' without a preceding 'contract'" when the real problem
   is a regression. Not fixed: outside this pass's R1-1…R1-6 bounds.
2. **R1-8 (P3) — duplicate front-matter keys last-win.** `phase: contract`
   then `phase: expand` in one record still passes, the second value
   silently overwriting the first. Not fixed, same reason. Noted plainly:
   this is a residual fail-open in `parse_front_matter`, the same function
   region R1-3's fix sits next to. A round-2 reviewer may legitimately
   judge that leaving it while closing R1-3 is inconsistent; that is a
   scope call for the orchestrator, not something this session resolved
   unilaterally.
3. **R1-10 (P3) — nothing checks a `migrate` record actually describes a
   throttled/resumable backfill.** The reviewer explicitly scoped this out
   of SCN-070 and to GOV-01-R06's backfill-throttling obligation. Not
   fixed. Still owned by a future slice.
4. **CI wiring remains absent.** No `.github/workflows` directory exists
   anywhere in this repo (re-verified this session). R1-5 is closed only
   at the local-aggregator level; the real migration-safety CI check, and
   passing `--require-dir` once records exist, remain an **explicit
   GOV-01-R04 obligation**, not an assumed one.
5. **The lint over the real tree is still vacuous.** `backend/migrations/records/`
   holds only `.gitkeep`, which is legitimate (R06's own OUT-of-scope line:
   no product schema exists). The difference from round 1 is that the
   vacuity is now *stated in the output* rather than invisible.
6. **Routing/ADR question** — whether GOV-01-R06 lint work should fall
   inside `veyro-critical-engineer`'s scope needs an ADR-005 amendment if
   so. See §1.
7. **`SCENARIOS.md` untouched.** SCN-MOD001-070 still reads
   `EXECUTED — PENDING INDEPENDENT REVIEW`. A fresh round-2 independent
   review is required before any promotion; this session is not eligible
   to perform or claim it.

---

## 7. Integrity / fail-closed compliance

- **No commit, no push, no stash, no reset, no checkout, no branch
  change.** `git rev-parse --short HEAD` = `e481b81`, unchanged from
  session start.
- **All pre-existing uncommitted work preserved.** Nothing was removed,
  reverted, or renamed — `git status --porcelain | grep -E "^( D|D |R )"`
  returns nothing. `git status --porcelain` went from **311** entries at
  session start to **318** at closeout; the count only grew.

  **The exactly six paths this session created or modified**, and nothing
  else:
  1. `tools/validate_migration_ordering.py` (M — was clean/committed)
  2. `tools/tests/test_validate_migration_ordering.py` (M — was clean/committed)
  3. `backend/migrations/TEMPLATE.md` (M — was clean/committed)
  4. `knowledge/05-QA/tools/run_regression.py` (M — **already** modified
     before this session; this session appended two `CHECKS` entries plus
     their explanatory comment and touched nothing else in the file)
  5. `knowledge/03-Modules/MOD-001/evidence/implementation/SCN070-ROUND1-REMEDIATION-2026-10-04.md` (new, this file)
  6. `knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py` (new)
  7. `knowledge/03-Modules/MOD-001/evidence/model-routing/SCN070_R1_REMEDIATION_RUNTIME_PROOF_2026-10-04.md` (new)

  Plus one **amendment appended** to the already-untracked
  `SCN070-MIGRATION-ORDERING-EXECUTION-2026-10-04.md` (R1-6), which was
  already a `??` entry before this session and so added no new count.
  (Seven paths listed; item 4 was pre-existing, so this session added six
  *new* porcelain entries.)

  **The +7 count delta is therefore not all this session's.** Stated
  rather than glossed: an mtime sweep of every porcelain entry at closeout
  shows the orchestrating/watchdog session concurrently wrote
  `AUTONOMOUS_CONVERGENCE_STATE.json`, `CURRENT_HANDOFF.md`,
  `CURRENT_STATE.md`, `REVIEW_IN_FLIGHT.md`, `SCENARIOS.md`,
  `DOM002-CONVERGENCE-DISPATCH-CONTROL-2026-10-04.md`,
  `SCN070-INDEPENDENT-REVIEW-DISPATCH-2026-10-04.md`, and
  `SCN070-R1-REMEDIATION-ACPX-RAW-2026-10-04.txt` inside the same window.
  **This session edited none of those** — in particular not `SCENARIOS.md`
  and not `CURRENT_STATE.md`/`CURRENT_HANDOFF.md`. A round-2 reviewer
  checking mtimes should attribute those to the parent session, and should
  not read the `SCENARIOS.md` mtime as a scenario promotion by this
  session: SCN-MOD001-070's entry still reads `EXECUTED — PENDING
  INDEPENDENT REVIEW (2026-10-04)`, unchanged.
- **`REVIEW_IN_FLIGHT.md` read and left untouched** (`current_claim: CLEAR`).
  No review was dispatched, so no claim was written — correct per that
  file's protocol, which governs dispatching, not remediating.
- **Not touched, at all:** DOM-002 round 5 (still interrupted/
  non-resumable, its 4+4 historical counters unchanged), BUG-048,
  BUG-049, BUG-050, SCN-MOD001-009, SCN-067, R04/ADR-010 A2, MOD-001
  certification, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, `SCENARIOS.md`,
  `REQUIREMENTS.md`, any `.claude/` file, and every baseline artifact.
- **Baselines re-verified** as part of A11: `verify_baselines.py` →
  `PASS — all 4 governing baseline hashes match PROJECT_INDEX.md exactly.`
- **Owner-reserved absolutes respected:** no spend, no paid service, no
  real member data (every fixture synthetic), no deploy/Production
  promotion, no material product/pricing/business/architecture/scope
  change.
- **Throwaway fixtures deleted at closeout:** `/tmp/scn070_r1fix/` (all
  subtrees) and the kill-check's own `tempfile` mirrors, which it removes
  in `finally`. Deletion confirmed — see §8.
- **Phase vocabulary treated as non-defect**, per the round-1 report's own
  verified finding: the scenario's "backfill" = TSD §24.2's
  "migrate/backfill" = the lint's `migrate`, a documented equivalence. No
  change made to `PHASE_ORDER`.

## 8. Closeout verification

Recorded at 12:13Z, after all edits and test runs:

- `/tmp/scn070_r1fix/` — removed, absence confirmed.
- `tools/validate_migration_ordering.py` SHA-256
  `17f6d8457d86d794750de62db368051f7abf6aab1d2f6d93285a3f479a1f80af`
- `tools/tests/test_validate_migration_ordering.py` SHA-256
  `49797b5ba0a75a8aa9e70e700776cf2c9063402d392c82831d0a6bf91b8e51af`
- `scn070_ordering_lint_mutation_killcheck.py` SHA-256
  `8fc9daac892307a15295a58f30e0e44cb9034d61049487364a52aea4aa5f88de`
- `knowledge/05-QA/tools/run_regression.py` SHA-256
  `22581aebd4a4b7e50615ca6e6c27ddab9049ce315682eeb156ec2c2f01aef21e`

The kill-check asserts the first two hashes itself on every run, so a
later session can detect drift between this record and the files it
describes without trusting this record's own numbers.

## 9. Deliberately left to the orchestrating session

`CURRENT_STATE.md` and `CURRENT_HANDOFF.md` were **not** updated by this
session, and that is intentional rather than an omission: the closeout
mtime sweep (§7) shows the parent/watchdog session writing both files
inside this session's own working window. A concurrent edit from here
would risk clobbering the parent's in-flight writes — the same class of
two-writer hazard this module already has a reconciliation record for
(`SCN-MOD001-009-EVIDENCE-RECONCILIATION-2026-10-04.md`). The
orchestrating session should record the pointer to this remediation record
in `CURRENT_STATE.md`/`CURRENT_HANDOFF.md` itself.

## 10. Next legal action

A **fresh-context independent round-2 review** of this remediation
(`veyro-security-reviewer` or `veyro-code-reviewer`, Opus, zero context
from this session), re-running the mutation battery in §5 and probing for
new fail-opens introduced by the R1-3/R1-4 changes. Per
`SESSION_BOOTSTRAP.md` §4, the dispatching session must write an
`IN_FLIGHT` claim in `REVIEW_IN_FLIGHT.md` **before** the dispatch call
returns. SCN-MOD001-070 may not be promoted before that round-2 verdict.

---

## Amendment 2026-10-04 (post round-2 review)

Round 2 (`../security/SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND2-2026-10-04.md`,
BLOCKED, P0=0/P1=0/P2=3/P3=4) confirmed R1-1's P1 and R1-2/R1-5/R1-6/R1-9
closed **by independent execution of this record's own mutation harness**.
Two claims in §2's table were **overstated** and are corrected here rather
than left standing:

- **R1-3 "FIXED (closed, not accepted-risk)"** — round 2: *partially*
  closed. Correct for `.yml`, `.md`, and real subdirectories; **open for
  symlinked subdirectories**, where `rglob` does not descend and
  `is_dir()` follows the link, so a destructive out-of-order `contract`
  behind a symlinked child produced exit 0 with no notice (R2-1).
- **R1-4 "FIXED"** — round 2: *partially* closed. Correct for an absent
  path; **open when the path exists but is not a directory**, where
  `--require-dir` was entirely inert (R2-3).
- **R1-8 (left unfixed here as P3)** — round 2 escalated it to **P2**
  (R2-2), taking up this record's own §6 item 2 invitation: rated on
  consequence rather than mechanism, a duplicated `phase:` key producing a
  green destructive `contract` is the same observable outcome as R1-3.

All three are now closed — see
`SCN070-ROUND2-REMEDIATION-2026-10-04.md`. The §2 table and §4/§5 outputs
above are left as the dated record of what was observed at this round's
12:13Z closeout (18 tests, 8 mutants); they are historical observations,
not current state. Current state is 29 tests and 11 mutants.

Positional test-number citations in §2's table (previously "tests 7-8",
"tests 11-14", etc.) were replaced with test *function names* — round-2
finding R2-6 showed positional references drift the moment a test is added.

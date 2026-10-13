---
doc: SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND2
module: MOD-001
requirement: GOV-01-R06 (Database-change policy/tooling), TSD §24.2
scenario: SCN-MOD001-070 (MIG · Blocker · negative)
round: 2
date: 2026-10-04
role: veyro-security-reviewer (Opus tier, fresh context)
verdict: BLOCKED
counts: P0=0 / P1=0 / P2=3 / P3=4
---

# SCN-MOD001-070 — Independent Security Review, Round 2

Fresh-context independent review of the round-1 remediation of the
GOV-01-R06 migration-ordering lint. This round replaces an earlier
round-2 attempt that was interrupted before producing any verdict.

## 1. Scope, identity, and independence

**Charge.** Decide R1-1 … R1-6 by execution, with specific attention to
two shapes observed in the interrupted attempt's partial output: a
regular file passed as `--records-dir` producing a vacuous PASS, and a
symlinked child directory hiding a destructive contract record. Classify
any genuine residue by priority and invariant, and distinguish
requirement violations from optional hardening.

**Independence.** This session performed no part of the implementation or
the round-1 remediation. It read the governing requirement
(`REQUIREMENTS.md` GOV-01-R06, §370-412), the governing scenario
(`SCENARIOS.md` SCN-MOD001-070, line 1652-1657), the round-1 report, the
round-1 remediation record, and the current code and tests, then executed
its own controls.

**Model/session identity — no self-attestation.** Declared model for this
session is `claude-opus-5[1m]`. Consistent with this project's convention
and `mr_verify.py`'s own documented finding that no environment variable
exposes the resolved model, **this report makes no self-attestation**. The
orchestrating session must run `mr_verify.py` against this session's
actual transcript:

    ~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/07c49161-b6ca-41c5-9157-ca7b05b4463c.jsonl

**Interrupted prior attempt.** `SCN070-ROUND2-ACPX-RAW-2026-10-04.txt` is
raw partial output with no verdict. It is treated here as a pointer to
two shapes worth probing, **not** as evidence and **not** as an approval.
Every finding below was independently reproduced in this session. (The
companion `SCN070-ROUND2-BOUNDED-ACPX-RAW-2026-10-04.txt` is the
watchdog's live capture of *this* session, not a prior attempt.)

**Constraints honored.** No product, tool, or test code was edited. No
scenario promoted, no module certified. DOM-002 round 5 not touched
(remains interrupted/non-resumable, outside scope). No unrelated slice
altered. `HEAD` = `e481b81`, unchanged; 321 uncommitted entries preserved.
All controls ran in `/tmp/scn070_r2`, never the real tree; the lint's and
test file's SHA-256 were confirmed unchanged across the mutation battery.

## 2. Verdict

**BLOCKED — P0=0 / P1=0 / P2=3 / P3=4.**

Round 1's single P1 (R1-1, the uncovered start-phase guard) is **genuinely
and decisively closed**, verified by independent execution of the mutation
battery rather than by trusting the remediation record. R1-2 … R1-6 and
R1-9 are also closed for the shapes they named. The remediation is real
work, honestly recorded, and materially improves the lint's decisiveness.

It is nonetheless **BLOCKED** for promotion: three P2 residues remain, and
two of them (R2-1, R2-2) are *fail-opens* in which a genuinely destructive,
genuinely out-of-order `contract` record produces a clean exit 0 and the
ordinary `PASS` line. That is the precise condition SCN-MOD001-070 — a
Blocker-tier negative scenario — exists to prove impossible. A lint that
decisively rejects the straightforward shape but is defeated by a
duplicated YAML key does not yet decisively enforce the invariant.

**SCN-MOD001-070 must remain `EXECUTED — PENDING INDEPENDENT REVIEW`. Not
promoted.**

## 3. What round 1's findings now look like — verified by execution

| Round-1 finding | Claimed | Round-2 verdict (by execution) |
|---|---|---|
| R1-1 (**P1**) start-phase guard uncovered, mutant M3 survives | FIXED | **CONFIRMED CLOSED.** M3 now KILLED by `unit`+`cli-lone`. Tests 7-8 reach the guard. |
| R1-2 (P2) `main()` exit-code contract uncovered, M5 survives | FIXED | **CONFIRMED CLOSED.** M5 now KILLED by all three controls. Tests 9-10 drive a real subprocess and assert the exit code. |
| R1-3 (P2) non-`.yaml`/nested records silently ignored | FIXED (closed) | **PARTIALLY CLOSED.** Correct for `.yml`, `.md`, and real subdirectories (M6/M7 killed; Control F). **Open for symlinked subdirectories — see R2-1.** |
| R1-4 (P2) typo'd `--records-dir` exits 0 with PASS | FIXED | **PARTIALLY CLOSED.** Correct for an *absent* path (M8 killed). **Open when the path exists but is not a directory — see R2-3.** |
| R1-5 (P2) lint invoked by no automated gate | FIXED (local); CI carried forward | **CLOSED AS SCOPED, honestly disclosed.** Registered in `run_regression.py`; that file's own comment states plainly that the gate is currently vacuous and `--require-dir` is not passed. No overclaim. See R2-7. |
| R1-6 (P2) evidence record not re-runnable | FIXED | **CONFIRMED CLOSED.** Amendment appended (not rewritten) at `SCN070-MIGRATION-ORDERING-EXECUTION-2026-10-04.md` §13, with literal re-runnable commands and verbatim stdout. |
| R1-9 (P3) hand-maintained test list / hardcoded count | FIXED | **CONFIRMED CLOSED.** Dynamic `test_*` discovery; 18/18 discovered and passing, matching 18 `def test_` on disk. |

### 3.1 Independently executed mutation battery

Ran the remediation's own harness
(`evidence/implementation/scn070_ordering_lint_mutation_killcheck.py`)
under `backend/.venv/bin/python`. Verbatim result:

    m0 baseline (unmutated): SANE — unit exit 0, PASS — all 18 tests passed
    M1 check_ordering returns [] immediately: KILLED by unit+cli-negative+cli-lone
    M2 ordering predicate accepts any skip-ahead: KILLED by unit+cli-negative
    M3 start-phase guard neutralized (R1-1, SURVIVED at round 1): KILLED by unit+cli-lone
    M4 validate_fields returns [] immediately: KILLED by unit
    M5 main() rejection exit code neutralized (R1-2, SURVIVED at round 1): KILLED by unit+cli-negative+cli-lone
    M6 discovery narrowed back to glob('*.yaml') (R1-3 fix removed): KILLED by unit
    M7 UNRECOGNIZED_RECORD_FILE suppressed (R1-3 fix removed): KILLED by unit
    M8 --require-dir neutralized (R1-4 fix removed): KILLED by unit
    8/8 mutations killed; survivors=[]

`tools/validate_migration_ordering.py` SHA-256
`17f6d8457d86d794750de62db368051f7abf6aab1d2f6d93285a3f479a1f80af` and
`tools/tests/test_validate_migration_ordering.py` SHA-256
`49797b5ba0a75a8aa9e70e700776cf2c9063402d392c82831d0a6bf91b8e51af`
confirmed identical before and after the battery.

**The two round-1 survivors are dead. R1-1's P1 is closed on executed
evidence, not on assertion.**

## 4. Findings

### R2-1 (P2) — a symlinked subdirectory inside the records dir hides a destructive out-of-order record behind a fully clean PASS

**Invariant violated:** record discovery is exhaustive — "never a silent
partial pass." The lint's own module docstring, "Record discovery
(hardened 2026-10-04, round-1 review finding R1-3)," states absolutely:
"Every other file **anywhere in that tree** … is reported as
`UNRECOGNIZED_RECORD_FILE`, not silently skipped." That claim is false.

**Mechanism.** `discover_records()` iterates `records_dir.rglob("*")`.
`rglob` does not descend through symlinked directories, so files beneath
one are never enumerated. The symlink itself reaches the loop, but
`path.is_dir()` follows the link and returns `True`, so the first branch
`continue`s — the symlink is neither recursed into nor reported. Both the
recursion and the reporting path miss it.

**Reproduced (decisive variant, Control E).** A records dir holding a
valid, complete `expand → migrate → switch → contract` set for `change_a`,
plus a symlinked child `q4/` whose target holds a lone
`0005_b_contract.yaml` for `change_b` — a destructive contract phase with
no predecessors at all:

    $ find mixed/ -follow -type f | sort
    mixed/0001_a_expand.yaml
    mixed/0002_a_migrate.yaml
    mixed/0003_a_switch.yaml
    mixed/0004_a_contract.yaml
    mixed/q4/0005_b_contract.yaml          <-- reachable, destructive, out of order

    $ python3 tools/validate_migration_ordering.py --records-dir mixed --require-dir
    Records dir checked: mixed

    PASS — every migration record is complete and phase-ordered correctly
    exit=0

**No `NOTICE` is printed.** Because real records *are* present, neither
vacuous-pass notice fires, so the single mitigating signal the round-1
remediation added is absent. This is a fully clean, indistinguishable
false PASS — strictly worse than the no-records symlink case (Control C),
which at least emits the vacuous-pass notice.

**Negative control proves it is specifically symlink blindness, not a
general subdirectory gap (Control F).** The identical shape with a *real*
subdirectory is correctly caught:

    - q4/0005_b_contract.yaml: UNRECOGNIZED_RECORD_FILE — not a '*.yaml' file
      directly inside the records dir … exit=1

**Positive control (Control G).** A symlinked `*.yaml` *file* placed
directly in the records dir is correctly read and rejected
(`OUT_OF_ORDER_PHASE`, exit 1). The gap is specific to symlinked
*directories*.

**Requirement, not optional hardening.** Symlink resistance in the
abstract would be hardening. What makes this a requirement-level defect is
that it reopens exactly the R1-3 defect class — the same observable
outcome round 1 rated P2 and the remediation recorded as "FIXED (closed,
not accepted-risk)" — in a shape the fix does not cover, while the tool's
own governing docstring now asserts the stronger closure. The durable
record therefore carries a false closure claim.

**Suggested remediation (not applied — review is read-only).** Treat a
symlink inside the records tree as a first-class discovery problem:
before the `is_dir()` branch, test `path.is_symlink()` and emit a problem
naming it. That fails closed without resolving link targets or widening
the walk, and it is testable with the fixture above. Narrowing the
docstring's absolute claim is **not** an adequate substitute — the clean
exit-0 PASS would survive.

### R2-2 (P2) — a duplicated `phase:` key lets a record whose declared phase is `contract` pass as `expand`

**Invariant violated:** the phase the record declares is the phase the
lint enforces.

**Mechanism.** `parse_front_matter()` assigns into a flat dict
(`fields[key.strip()] = value.strip()`) with no duplicate-key detection,
so the last occurrence silently wins. A record a human reads as
`contract` is linted as whatever the final `phase:` line says.

**Reproduced (Control I).** One record, destructive by its own
`lock_impact`, declaring `phase: contract` in the authoritative first
position and `phase: expand` after the other fields:

    ---
    change_id: add_widget_column
    phase: contract
    owner: j@e.com
    lock_impact: DROP COLUMN — destructive, rewrites table
    rollback_strategy: restore from backup
    validation_query: SELECT 1
    phase: expand
    ---

    $ python3 tools/validate_migration_ordering.py --records-dir dupkey --require-dir
    PASS — every migration record is complete and phase-ordered correctly
    exit=0

No `NOTICE`, no problem line, exit 0. **Order dependence confirmed
(Control J):** the same record with the two `phase:` lines transposed is
correctly rejected (`OUT_OF_ORDER_PHASE … starts at 'contract'`, exit 1),
proving the outcome turns purely on which duplicate lands last.

**Severity escalated from round 1's P3, which the remediation itself
invited.** The round-1 remediation's §6 item 2 recorded this as unfixed
and wrote, verbatim: "this is a residual fail-open in `parse_front_matter`
… A round-2 reviewer may legitimately judge that leaving it while closing
R1-3 is inconsistent; that is a scope call for the orchestrator." Taking
that judgment: **it is inconsistent, and P3 understates it.** R1-3 was
rated P2 for letting an out-of-order destructive record pass green. This
produces the identical observable outcome through a shorter path, needs no
adversary — a careless copy-paste while editing a record is enough — and
is invisible to review because the human-authoritative first `phase:` line
reads correctly. Round 1 appears to have rated it on mechanism
(duplicate-key parsing) rather than on consequence (a destructive contract
record passing green); rated on consequence it is P2.

**Requirement, not optional hardening.** It directly defeats GOV-01-R06's
own acceptance criterion, "the lint rejects an out-of-order destructive
migration," and SCN-MOD001-070's own expected result.

**Suggested remediation (not applied).** Reject duplicate keys in
`parse_front_matter` as a `DUPLICATE_FRONT_MATTER_KEY` problem rather than
resolving them. Silently picking either occurrence is a guess about author
intent; refusing is the fail-closed answer and needs about three lines.

### R2-3 (P2) — `--require-dir` does not fail closed when `--records-dir` resolves to an existing non-directory

**Invariant violated:** fail closed on an unusable records path. This is
the flag's own stated contract — `--help`: "Any future CI wiring should
pass this so a typo'd or relocated path cannot pass green forever"; and
`validate_directory`'s docstring: "a typo'd or relocated records path must
fail closed, not report a vacuous pass."

**Mechanism.** The guard is `if not records_dir.exists()`. A regular file
exists, so the `require_dir` branch is skipped entirely. `Path.rglob` on a
non-directory yields nothing without raising, so discovery returns empty
and the run reports PASS.

**Reproduced (Controls A and B).** A plain text file passed as the records
dir, **with** `--require-dir`:

    $ python3 tools/validate_migration_ordering.py --records-dir plainfile.txt --require-dir
    Records dir checked: plainfile.txt
    NOTICE: records dir exists but contains no migration records — vacuous pass, no record was checked.
    PASS — every migration record is complete and phase-ordered correctly
    exit=0

Identical output without the flag, so **the flag is inert for this
shape.**

**Why P2 and not P1.** The vacuous-pass `NOTICE` does fire, so this is not
silent to a human reading stdout. But the flag exists precisely so a
machine gate can rely on the **exit code**, and the exit code is 0. A
future CI job that follows this tool's own `--help` instruction would pass
green forever against a path that is a file — a stale path, a botched
checkout, a `>` redirect that created a file where a directory was
expected. R1-4's fix is correct for the absent-path shape it was written
for and incomplete for this one.

**Requirement, not optional hardening** — the tool's own documented
fail-closed contract is falsified.

**Suggested remediation (not applied).** Change the condition to
`if not records_dir.is_dir()`, and distinguish the two causes in the
message (absent vs. exists-but-not-a-directory) so the diagnostic still
names the real problem. Note that `is_dir()` follows symlinks, so a
symlink to a real directory keeps working.

### R2-4 (P3) — a broken `*.yaml` symlink crashes with an uncaught traceback

**Reproduced (Control H).** A dangling symlink named `0001_x.yaml`
directly inside the records dir is classified as a record, then
`parse_front_matter`'s `read_text` raises an uncaught `FileNotFoundError`
and the process dies with a traceback.

**P3, not higher: this fails closed.** The exit status is non-zero and the
failure is loud. The defect is diagnostic quality only — a stack trace
instead of a named problem line, inconsistent with the tool's otherwise
uniform "name every problem record" contract. `RecordError` already exists
as the right vehicle; catching `OSError`/`UnicodeDecodeError` alongside it
in `validate_directory`'s existing `try` would also cover the
unreadable-permissions and non-UTF-8 cases.

### R2-5 (P3) — backward-jump diagnostic misnames the cause (round-1 R1-7, carried forward)

**Reproduced (Control K).** A fifth `expand` after a complete valid
four-phase sequence reports: "jumps to 'expand' without a preceding
'contract'" when the real problem is a *regression* to an earlier phase.
Fails closed, exit 1 — safe direction, misleading text. Accurately
disclosed as unfixed in the remediation's §6 item 1. No escalation.

### R2-6 (P3) — test-file enumeration and the remediation table disagree with the actual test count

The test file's docstring enumerates through "15-17" while 18 `def test_`
functions exist on disk; the remediation record's table cites "tests
15-18" for R1-4 and "tests 11-14" for R1-3. Record accuracy only, and the
R1-9 fix makes it harmless in execution: discovery is dynamic, the runner
prints its own count, and 18/18 was confirmed. Worth a one-line docstring
correction so a later reader does not conclude a test is missing.

### R2-7 (P3) — the automated gate is real but vacuous, and CI wiring is still absent

The lint and its unit suite are both registered in
`knowledge/05-QA/tools/run_regression.py`. The lint entry is vacuous today
(`backend/migrations/records/` holds only `.gitkeep`, legitimate under
R06's own OUT-of-scope line), and `--require-dir` is not passed. **This is
disclosed, not concealed** — `run_regression.py`'s own comment block says
so in terms, and the remediation's §6 items 4-5 repeat it. The genuinely
load-bearing half, the unit suite, is registered and is what kills M3 and
M5. No new defect; recorded so the carried-forward GOV-01-R04 obligation
(real CI wiring, and `--require-dir` once records exist) does not get lost
behind R1-5's "FIXED" label. Note R2-3: adding `--require-dir` to a CI
invocation will not by itself protect against a path that is a file.

## 5. What the governing acceptance criteria actually require

`REQUIREMENTS.md` GOV-01-R06 acceptance: "the lint rejects an out-of-order
destructive migration; a valid 4-phase migration passes; rollback strategy
is present and testable for at least the synthetic case."

- Rejects an out-of-order destructive migration — **met for the
  straightforward shape** (Control D: lone `contract`, exit 1,
  `OUT_OF_ORDER_PHASE` naming change_id, phase found, and phase needed),
  and now decisively controlled (M3 killed). **Defeated by R2-1 and R2-2.**
- A valid 4-phase migration passes — **met** (test 2; Control E's
  `change_a` set).
- Rollback strategy present and testable — **met**: `rollback_strategy` is
  a required non-empty field, with a negative control (test 4).

`SCENARIOS.md` SCN-MOD001-070's expected result ("the migration-safety
lint rejects it") is met for its literal shape and defeated by two
evasion shapes. For a **Blocker**-tier negative scenario whose entire
purpose is fail-closed enforcement, surviving evasion shapes block
promotion — particularly R2-2, which is reachable by ordinary authoring
error rather than adversarial effort.

**Phase vocabulary — not a defect, consistent with round 1.** The
scenario's "backfill" maps to TSD §24.2's "migrate/backfill" and the
lint's `migrate`. Re-confirmed; no finding.

## 6. Executed evidence — commands and results

All controls ran in `/tmp/scn070_r2` against the real tool via
`--records-dir`. The real repository tree was never written.

| # | Control | Result | Finding |
|---|---|---|---|
| A | regular file as `--records-dir`, no flag | exit 0, PASS + vacuous NOTICE | R2-3 |
| B | regular file as `--records-dir`, `--require-dir` | exit 0, PASS + vacuous NOTICE — flag inert | R2-3 |
| C | symlinked child, no other records | exit 0, PASS + vacuous NOTICE | R2-1 |
| D | lone destructive `contract`, placed directly (**positive control**) | exit 1, `OUT_OF_ORDER_PHASE` | — (passes) |
| E | valid 4-phase set **+** symlinked child hiding a lone destructive `contract` | **exit 0, clean PASS, no NOTICE** | **R2-1, decisive** |
| F | same shape, **real** subdir (**negative control**) | exit 1, `UNRECOGNIZED_RECORD_FILE` | — (proves symlink-specific) |
| G | symlinked `*.yaml` **file** directly in dir | exit 1, `OUT_OF_ORDER_PHASE` | — (passes) |
| H | broken `*.yaml` symlink | uncaught `FileNotFoundError` traceback, non-zero | R2-4 |
| I | duplicated `phase:` — `contract` then `expand` | **exit 0, clean PASS, no NOTICE** | **R2-2, decisive** |
| J | duplicated `phase:` transposed (**order control**) | exit 1, `OUT_OF_ORDER_PHASE` | — (proves last-wins) |
| K | backward regression after valid 4-phase | exit 1, cause misnamed | R2-5 |

Additional executed checks:

- Unit suite, documented direct-invocation path:
  `python3 tools/tests/test_validate_migration_ordering.py` →
  **`PASS — all 18 tests passed (discovered dynamically, not hand-listed.)`**,
  exit 0; `grep -c "^def test_"` → 18 (counts agree).
- Lint over the live tree: exit 0 with the vacuous-pass NOTICE —
  consistent with `backend/migrations/records/` holding only `.gitkeep`.
- Mutation battery: 8/8 killed, survivors `[]`, both round-1 survivors
  dead; tool and test SHA-256 unchanged (§3.1).
- `git rev-parse --short HEAD` → `e481b81`, unchanged; `git status
  --porcelain | wc -l` → 321 entries preserved.

**Deliberately not executed, to stay bounded per charge:** no Docker,
Colima, or Postgres work; no full backend suite; no aggregate
`run_regression.py` run (its two known pre-existing failure artifacts —
the retired-CAP-007 `test_bash_guard.py` suite and the
`CURRENT_HANDOFF.md` evidence-integrity staleness artifact of this
project's no-commit-mid-round convention — would have dominated the
result without informing this verdict). None of these bear on the
findings above, every one of which is reproducible with the stdlib-only
lint and a temporary directory.

## 7. Remaining blockers for SCN-MOD001-070 promotion

1. **R2-1 (P2)** — symlinked subdirectory hides records behind a clean
   exit-0 PASS; R1-3's documented closure claim is currently false.
2. **R2-2 (P2)** — duplicated `phase:` key lets a declared-`contract`
   record pass as `expand`, exit 0.
3. **R2-3 (P2)** — `--require-dir` is inert when the path exists but is
   not a directory.

P3s (R2-4 … R2-7) are **non-blocking**. R2-6 is a one-line docstring fix;
R2-7 is a disclosure-complete carried-forward GOV-01-R04 obligation.

Promotion also still requires, unchanged: a fresh independent round-3
review of whatever remediation closes the three P2s. This review does not
and cannot promote the scenario.

## 8. Recommended next legal action

1. An **implementation-tier** session (routine tier — none of the three
   fixes requires Opus-reserved architectural judgment; GOV-01-R06 lint
   work is outside `ADR-005` Decision 1's three-slice
   `veyro-critical-engineer` boundary, consistent with the round-1
   remediation's own recorded routing determination) closes R2-1, R2-2,
   and R2-3, in that order. Each fix should be regression-locked with the
   fixture that demonstrates it here, and each new test proven
   non-vacuous against the pre-fix code before being accepted.
2. Extend `scn070_ordering_lint_mutation_killcheck.py` with three
   mutants corresponding to the new guards (symlink-reporting removed;
   duplicate-key rejection removed; `is_dir()` reverted to `exists()`),
   so the next round inherits a battery that covers them.
3. Correct the false closure language: the lint's "Record discovery"
   docstring and the round-1 remediation's R1-3 row currently assert a
   completeness the code does not have. Correct the **code** first —
   narrowing the claim alone would leave Control E's clean exit-0 PASS in
   place.
4. Then dispatch a **fresh independent round-3 review**, writing an
   `IN_FLIGHT` claim in `REVIEW_IN_FLIGHT.md` before the dispatch call
   returns, per `SESSION_BOOTSTRAP.md` §4.

Do **not** promote SCN-MOD001-070, close GOV-01-R06, or certify MOD-001 on
this round's verdict.

## 9. Record-integrity statement

- No product, tool, or test file was created, edited, or deleted by this
  session. No scenario promoted; no module certified.
- `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`, and `REVIEW_IN_FLIGHT.md` were
  **not** written by this session. `REVIEW_IN_FLIGHT.md`'s
  `current_claim` already named this bounded round-2 replacement dispatch
  at session start, so no new claim was written. The orchestrating session
  should record this report's verdict in the durable state files and clear
  the claim **on result recorded**, per that file's own protocol.
- DOM-002 round 5 untouched (interrupted/non-resumable, out of scope).
  R04/ADR-010 A2, SCN-067, BUG-048, and SCN-MOD001-009 untouched. No
  unrelated slice altered. WIP=1 preserved; MOD-002 remains locked.
- No commit, push, stash, reset, checkout, or branch change.
- Round 1's evidence remains, on this round's independent reading,
  factually honest. The remediation record is likewise honest, including
  about what it left undone — R2-2 exists as a finding largely *because*
  that record disclosed it and explicitly asked a round-2 reviewer to rule
  on its severity. The BLOCKED verdict is about residual fail-opens in the
  code, not about record integrity.
- This report makes no model self-attestation (§1).

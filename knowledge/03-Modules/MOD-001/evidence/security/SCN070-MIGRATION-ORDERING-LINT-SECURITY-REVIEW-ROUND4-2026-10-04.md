---
doc: SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND4
module: MOD-001
requirement: GOV-01-R06 (Database-change policy/tooling), TSD §24.2
scenario: SCN-MOD001-070 (MIG · Blocker · negative)
round: 4 (exceptional, authorized by SCN070-CONVERGENCE-ASSESSMENT-2026-10-04.md)
date: 2026-10-04
verdict: BLOCKED
counts: P0=0 / P1=0 / P2=2 / P3=4
convergence: NON_CONVERGING applies — a same-invariant fail-open survives
---

# SCN-MOD001-070 / GOV-01-R06 — Independent Security & Scenario Review, Round 4

## 1. Independence statement

Fresh-context reviewer with no memory of rounds 1–3, of the retained
implementation session, or of the interrupted earlier round-4 launch. No
prior-session claim was accepted on its text; every executable claim in this
report was re-executed in this session. I did not author, and have not
previously reviewed, any of the artifacts under review — no self-approval.
I was READ-ONLY on implementation: no product code, tool, or test was
modified, `REVIEW_IN_FLIGHT.md` was not touched, the scenario was not
promoted, and all mutation drills were performed on throwaway copies under
`/tmp`. Verified after all drills:

```
$ shasum -a 256 tools/validate_migration_ordering.py tools/tests/test_validate_migration_ordering.py
5738c9510904b0e80c2730ce4e1b97a2e7935289951a13084729b58254c0539e  tools/validate_migration_ordering.py
10c2872be3eb0aa5ce4b28416444c9b6ad56a09e94877143a3dd88259814f37c  tools/tests/test_validate_migration_ordering.py
```

Both match the SHA-256 values the remediation record itself asserts (§8),
so the reviewed bytes are the remediated bytes and nothing shifted under
this review. `git rev-parse HEAD` = `e481b814a80923849dddfe7a49319112aae7b023`,
unchanged. The only file this session created is this report.

## 2. Model / session attestation

- Resolved runtime model id: `claude-opus-5` (Opus 5, 1M context).
- Agent id: `ac2bde1b039c3617d`.
- Parent session: `abd3a77b-0601-45b7-90ab-a7ea3b4ac69a`.
- Transcript: `~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/abd3a77b-0601-45b7-90ab-a7ea3b4ac69a/subagents/agent-ac2bde1b039c3617d.jsonl`
  — identified as mine by grep, not assumption: it contains 12 occurrences
  of this session's own unique `/tmp/scn070r4` drill path and carries
  `"agentId":"ac2bde1b039c3617d"`.

Executed, not claimed:

```
$ backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py \
    .../subagents/agent-ac2bde1b039c3617d.jsonl opus scn070-round4-independent-review
{
  "verdict": "PASS",
  "reason": "49 turn(s), 100% consistent, model 'claude-opus-5' matches required tier 'opus'.",
  "models_observed": ["claude-opus-5"],
  "expected_tier": "opus"
}
```

Run mid-review, so the turn count will be higher at closeout; the
orchestrator should re-run it against the final transcript.

## 3. Baseline integrity

```
$ backend/.venv/bin/python knowledge/00-System/verify_baselines.py
Checked 4 of 4 expected governing baselines ...
  [MATCH] Gym_OS_Master_Product_Blueprint_v1_English.docx: 80f4b381...426ef
  [MATCH] Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx: 0d41c8a1...158e8
  [MATCH] Veyro_Engineering_Implementation_Plan_v1.4.1_..._GOVERNING_BASELINE.docx: e5b5ec3b...866b6
  [MATCH] veyro-product-experience-design: c96f77abdf4345b231a60b37f832d76ac82cf52fb8b00ae3066f20bb10a36dbb
PASS — all 4 governing baseline hashes match .../PROJECT_INDEX.md exactly.
```

**4/4 PASS.**

## 4. Scope

Bounded exactly as tasked: the architectural root-cause fix in
`tools/validate_migration_ordering.py` (glob-driven discovery replaced by
explicit error-reporting traversal, `enumerate_tree()`), its negative and
mutation tests, `SCN070-ROUND3-REMEDIATION-2026-10-04.md`,
`scn070_ordering_lint_mutation_killcheck.py`, the round-3 report's R3-1
section, and the SCN-MOD001-070 / GOV-01-R06 scenario and requirement rows.
Central question: **does the changed strategy eliminate the
exhaustive-discovery fail-open invariant family (R1-3 / R2-1 / R2-3 /
R3-1), or does a same-invariant fail-open survive?**

Not re-opened: R2-1, R2-2, R2-3 (closed at round 3). R3-2/R3-3/R3-4 checked
for recurrence or regression only, not re-litigated. DOM-002 not inspected.

## 5. Executed checks

All drills ran against the current repo code from `/tmp/scn070r4`, using a
synthetic record writer (6 valid front-matter fields, no real data).

Unit suite, exact count:

```
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_migration_ordering.py -q
....................................                                     [100%]
36 passed in 0.47s
```

R3-1's exact pre-fix shape, mode-000 records dir holding a lone destructive
`contract`, both flag states:

```
### A1 mode-000 ROOT w/ destructive record, WITH --require-dir
BLOCKED: 1 problem(s) found:
  - /tmp/scn070r4/a: UNREADABLE_RECORDS_PATH — could not enumerate this directory (Permission denied), so any migration record under it would go unchecked; a tree that cannot be read must never report a pass
exit=1

### A2 same, WITHOUT --require-dir
BLOCKED: 1 problem(s) found:
  - /tmp/scn070r4/a: UNREADABLE_RECORDS_PATH — ...
exit=1
```

No `PASS` line and no "contains no migration records" notice in either —
the named R3-1 shape is genuinely closed, with and without the flag.

The decisive new probe (see R4-1): a records directory that **exists and is
readable in itself** and holds the same destructive record, but whose
**parent** directory is mode 000:

```
### I1 unreadable PARENT, WITHOUT --require-dir  (the default invocation)
Records dir checked: /tmp/scn070r4/i/parent/records
NOTICE: records dir does not exist — vacuous pass, no record was checked. Pass --require-dir to fail closed on a missing path.

PASS — every migration record is complete and phase-ordered correctly (or no records exist yet).
exit=0

### I2 same, WITH --require-dir
BLOCKED: 1 problem(s) found:
  - /tmp/scn070r4/i/parent/records: MISSING_RECORDS_DIR — --require-dir was set but this directory does not exist; a typo'd or relocated records path must fail closed, not report a vacuous pass
exit=1
```

The record's presence under that path was confirmed in the same drill by
temporarily restoring the parent's mode and listing it
(`0001_destructive_contract.yaml`), then re-locking.

## 6. Per-shape fail-closed results

Positive controls first — a guard that fires unconditionally is as defective
as one that never fires.

| # | Shape | Expected | Observed | Result |
|---|---|---|---|---|
| P1 | readable, complete valid 4-phase set | exit 0, real PASS, no notice | exit **0**, PASS, no notice | OK |
| P2 | readable empty dir | exit 0, PASS + honest vacuous notice | exit **0**, PASS + "contains no migration records" | OK |
| P3 | readable live tree, no args (`backend/migrations/records`) | exit 0 + honest notice | exit **0**, PASS + honest notice | OK |
| N1 | readable lone destructive `contract` | exit 1, `OUT_OF_ORDER_PHASE` | exit **1**, names `0001_destructive_contract.yaml`, change_id, and required `expand` | OK |
| A1 | mode-000 **root** + destructive record, `--require-dir` | named nonzero | exit **1**, `UNREADABLE_RECORDS_PATH` | OK |
| A2 | same, **without** `--require-dir` | named nonzero | exit **1**, `UNREADABLE_RECORDS_PATH` | OK |
| B1 | mode-000 **nested child** `q4/`, valid 4-phase set at top | named nonzero | exit **1**, `q4: UNREADABLE_RECORDS_PATH` (relative path) | OK |
| B2 | mode-000 **two levels down** `q4/deep/` | named nonzero | exit **1**, `q4/deep: UNREADABLE_RECORDS_PATH` | OK |
| E1 | dangling/broken `.yaml` symlink | named nonzero | exit **1**, `SYMLINK_IN_RECORDS_TREE` | OK |
| F1 | symlinked **subtree** hiding destructive record | named nonzero | exit **1**, `q4: SYMLINK_IN_RECORDS_TREE` | OK |
| G1 | recursive self-symlink (`g/loop -> g`) | named nonzero, no hang | exit **1**, `loop: SYMLINK_IN_RECORDS_TREE`, terminated immediately | OK |
| H1 | symlinked **child record file**, valid destructive target | named nonzero | exit **1**, `0002_link.yaml: SYMLINK_IN_RECORDS_TREE` | OK |
| C1 | mode-000 **individual record file** | named nonzero | exit **1** via raw `PermissionError` traceback — fail-closed, **not named** | R4-3 (P3) |
| D1 | non-UTF-8 record file | named nonzero | exit **1** via raw `UnicodeDecodeError` traceback — fail-closed, **not named** | R4-3 (P3) |
| J1 | record disappears mid-traversal (staged: deleted between `scandir` and classification) | named nonzero | raises `FileNotFoundError` — fail-closed, **not named** | R4-3 (P3) |
| **I1** | **records dir real + holds destructive record, parent mode 000, default invocation** | **named nonzero** | **exit 0, PASS, false NOTICE "records dir does not exist"** | **R4-1 (P2) — FAIL-OPEN** |
| I2 | same, with `--require-dir` | correct named nonzero | exit 1 but wrong reason: `MISSING_RECORDS_DIR` ("does not exist") | R4-1 (P2) |

## 7. Mutation results

The authored battery, re-run by me (not quoted from the record):

```
$ backend/.venv/bin/python knowledge/.../scn070_ordering_lint_mutation_killcheck.py
m0 baseline (unmutated): SANE — unit exit 0, PASS — all 36 tests passed
M1..M13 : all KILLED
13/13 mutations killed; survivors=[]
round-1 survivors now killed: ['M3 ... (R1-1)', 'M5 ... (R1-2)']
real tool sha256 unchanged:  5738c951...0539e
real test sha256 unchanged:  10c2872b...4f37c
```

Killcheck file SHA-256 `7aa1a487555f91c4b5b197516368faef6f7c2c16a8de11d95ccdc2bcb96cf213`
matches the remediation record's §8 assertion.

Independent drills in `/tmp/scn070r4_mut` (throwaway copies; repo untouched,
re-verified by hash above):

| Mutant | Change | Result |
|---|---|---|
| MUT-A | delete the `UNREADABLE_RECORDS_PATH` `problems.append(...)`, keep the `continue` | **5 failed, 31 passed** — tests are load-bearing, not vacuous |
| MUT-B | revert `enumerate_tree` body to `return sorted(root.rglob("*")), []` (the original error-suppressing enumerator) | **5 failed, 31 passed** |
| MUT-C | make the traversal guard fire **unconditionally** (blanket fail-closed) | **27 failed, 9 passed** — positive controls genuinely discriminate |

MUT-A/MUT-B both fail `test_live_chmod_000_directory_fails_closed` and
`test_cli_unenumerable_root_exits_1_with_no_false_vacuous_notice`, which
proves those two live-`chmod` tests actually execute on this host rather
than taking their early-return path (relevant to R4-4).

**Surviving mutant reported honestly:** none in the authored 13-mutant set
or in my three independent mutants. That is precisely the limit the
remediation record itself states (§7 item 8) — a battery defined by the
fixes cannot discover a fail-open nobody wrote a guard for. R4-1 is exactly
such a defect: it is live right now while all 36 tests and all 13 mutants
report green.

## 8. Findings

| id | sev | finding |
|---|---|---|
| **R4-1** | **P2** | **Same-invariant fail-open survives the architectural fix.** `validate_directory` (`tools/validate_migration_ordering.py:322-335`) gates the hardened enumerator behind `records_dir.is_dir()` / `records_dir.exists()`, and `main()` (line 397) repeats `args.records_dir.exists()`. `pathlib` swallows `PermissionError` in both predicates and returns `False` — the *identical* error-suppression property that made `rglob` the root cause. A records directory that exists and holds a destructive out-of-order `contract`, but whose parent is unreadable, therefore never reaches `enumerate_tree()` at all: exit **0**, the ordinary `PASS` line, and a NOTICE affirmatively stating the directory "does not exist". That is R3-1's exact observable shape, relocated from the enumerator to the predicate that gates it. Aggravating: `knowledge/05-QA/tools/run_regression.py:61-62` invokes the lint with **no** `--require-dir` (deliberately, per its own comment), so the only automated invocation that exists is the vulnerable one. With `--require-dir` the exit is 1 but the named reason is wrong (`MISSING_RECORDS_DIR`, "does not exist"), pointing an operator at a typo instead of a permission fault. Zero tests cover this shape; the full 36/36 suite and 13/13 battery pass with it live. |
| **R4-2** | **P2** | **Evidence record asserts a safety property that is demonstrably false, on exactly this code path.** `SCN070-ROUND3-REMEDIATION-2026-10-04.md` §7 item 1 correctly identifies `validate_directory`'s `records_dir.is_dir()` and `discover_records`'s `path.is_symlink()` as unguarded, then states the consequence: "On a tree where those raise, the tool dies with a traceback — **fail-closed (nonzero), not fail-open** — but not a named problem." Those two `pathlib` methods do not raise; they return `False` on `OSError`. The stated consequence is wrong in the reassuring direction, and the real consequence (R4-1) is a fail-open. This is the single place in the record that addresses the surviving defect's location, it was reasoned rather than executed, and it is the sentence a governance reader would rely on when judging whether the root cause was eliminated. The record's own §7 closing paragraph correctly declines to claim elimination — but item 1 is offered as "the honest boundary of what was proven", and that boundary is drawn in the wrong place. |
| R4-3 | P3 | Unreadable individual record file, non-UTF-8 record file, and a record that disappears mid-traversal all terminate with raw `PermissionError` / `UnicodeDecodeError` / `FileNotFoundError` tracebacks. All three are nonzero and therefore fail-**closed**, not fail-open, but they are outside the tool's named-problem vocabulary. The first two are the disclosed, carried R2-4 residual (record §7 item 2) — no regression. The mid-traversal case is a newly-enumerated member of the same residual class, not previously listed. |
| R4-4 | P3 | `test_live_chmod_000_directory_fails_closed` and `test_cli_unenumerable_root_exits_1_with_no_false_vacuous_notice` use a bare `return` rather than `pytest.skip()` when the host does not enforce mode 000. On such a host they report as PASSED with no assertion executed, and the headline "36 passed" would silently overstate coverage. On this host they genuinely run (proven by MUT-A/MUT-B). Reporting hygiene only. |
| R4-5 | P3 | Docstring of `test_cli_unenumerable_root_exits_1_with_no_false_vacuous_notice` opens by describing itself as "driven by an injected failure via a sitecustomize-free wrapper" and then states it uses the live `chmod` mechanism. The first clause describes a mechanism the test does not use. |
| R4-6 | P3 | `SCENARIOS.md:1657`'s execution-evidence pointer for SCN-MOD001-070 still names only the round-1 execution record and "6/6 unit tests". Three remediation rounds and 36 tests later, a reader following that row does not reach current state. Accurate as a historical pointer, stale as a state pointer — reconciliation item, not a defect in the fix. |

### P3 carry-forwards — recurrence/regression check only

- **R3-2** (unknown front-matter keys silently ignored): reproduced
  unchanged. A decoy `Phase: expand` alongside the authoritative
  `phase: contract` is ignored and `contract` is enforced — reader/enforcer
  mismatch persists, **no ordering bypass**, no regression.
- **R3-3** (absolute host paths printed): the new `UNREADABLE_RECORDS_PATH`
  message prints an absolute path for the root case only (A1); nested cases
  are relative (B1, B2). The absolute records-dir path is already printed
  unconditionally on the "Records dir checked:" line, so no widening. No
  regression.
- **R3-4** (no CI wiring): re-verified — `.github/workflows` does not exist;
  `run_regression.py` is still the only registration and still omits
  `--require-dir`. Unchanged, and it is what makes R4-1 reachable in
  practice.

### Evidence-accuracy audit of SCN070-ROUND3-REMEDIATION-2026-10-04.md

Every executable claim I could re-run reproduced from the record's own text:
36/36 unit tests; 13/13 mutants with `survivors=[]` and both round-1
survivors killed; the three asserted SHA-256 values (tool, test, killcheck)
all match byte-for-byte; `HEAD = e481b81`; control A5 (live tree, no args)
reproduces exactly including the honest notice; `.github/workflows` absent
as stated. The record is unusually disciplined — it labels itself NOT
REVIEWED / NOT PROMOTED, declines to declare convergence, lists eight
limitations it did not close, and §7 item 9 self-reports a discrepancy in
the round-3 *review* report (`HEAD = 3552299`, which I confirmed is wrong
against the actual `e481b81`) rather than silently editing another
reviewer's artifact. It honestly distinguishes demonstrated from inferred
almost everywhere. The one exception is R4-2, and it is material: the
unguarded-predicate consequence was inferred, stated as fact, and is false.

## 9. Root-cause invariant family — eliminated or surviving?

**A same-invariant fail-open survives. The family is not eliminated.**

The remediation did real work: `enumerate_tree()` is a genuine improvement,
every unenumerable *subtree* now fails closed with a named error at any
depth, and the named R3-1 shape is dead with and without `--require-dir`.
But the invariant at stake was never "`rglob` specifically suppresses
errors" — it was "**this tool cannot distinguish a path it could not read
from a path with nothing in it**." The fix replaced one error-suppressing
stdlib call inside the walker while leaving two more (`Path.is_dir()`,
`Path.exists()`) on the gate *in front of* the walker, in the very function
that decides whether the walker runs at all. The observable failure is
unchanged from R3-1: exit 0, the ordinary `PASS`, and a NOTICE affirmatively
asserting absence, over a tree containing a destructive out-of-order
`contract`. Only the triggering mode moved — from an unreadable records dir
to an unreadable parent of that dir.

Per `SCN070-CONVERGENCE-ASSESSMENT-2026-10-04.md`: *"If the remediation does
not demonstrably eliminate the root cause or introduces another
same-invariant fail-open, mark `NON_CONVERGING` instead of cycling."*
That condition is met. **`NON_CONVERGING` applies — this should not be
cycled into a round 5.** The reviewer does not set convergence status; that
is the orchestrator's/governance's action on this finding.

For the record, the shape of a real fix is narrow and known: resolve the
exists/is-dir/unreadable distinction with a single guarded `os.stat()` (or
`os.scandir()`) whose `OSError` is caught and classified, so that
"unreadable" is a third outcome alongside "absent" and "present" rather
than being folded into "absent". I did not implement it — read-only.

## 10. Verdict

**BLOCKED.** P0=0, P1=0, **P2=2**, P3=4.

SCN-MOD001-070 remains **EXECUTED — NOT PROMOTED**. GOV-01-R06's
"never a silent partial pass" contract is not yet satisfied: a tree holding
a destructive out-of-order migration can still produce exit 0 and a `PASS`
line under the default invocation, which is the invocation the only
automated caller uses.

## 11. Limits — what I did NOT check

- Did not run the full backend suite or any Docker/Postgres probe (out of
  scope, wall-clock bound).
- Did not re-litigate R2-1, R2-2, R2-3 (closed at round 3) beyond confirming
  their guards still fire (E1/F1/G1/H1, and MUT-C's positive controls).
- Did not audit the round-1 or round-2 reports, DOM-002, or anything outside
  the six scoped artifacts.
- Did not attempt an exhaustive audit of every stdlib call in the tool for
  error suppression; I probed the two the remediation record itself named
  plus `rglob`'s replacement. Other suppressing calls may remain — notably
  `entry.is_dir(follow_symlinks=False)`'s `except OSError: descend = False`
  at `enumerate_tree` line 251, which silently declines to descend without
  recording a problem. I reasoned (did not stage) that an entry hitting it
  is still reported as an entry and then becomes either
  `UNRECOGNIZED_RECORD_FILE` or a read error, so it appears fail-closed —
  but that is **inferred, not demonstrated**, and I could not stage a
  filesystem where a child `stat` fails after its parent `scandir` succeeds.
- Did not verify the `mr_verify.py` tool's own correctness, only ran it.
- The two live-`chmod` drills depend on this host (uid 501, macOS/APFS)
  enforcing mode 000; it does. Results may differ as root or on a
  permission-ignoring mount.
- No implementation change, no promotion, no `REVIEW_IN_FLIGHT.md` edit, no
  convergence-status change. Repo integrity re-verified by hash after every
  drill.

---
doc: SCN070-ROUND5-ROOTCAUSE-IMPLEMENTATION
module: MOD-001
requirement: GOV-01-R06 (Database-change policy/tooling), TSD §24.2
scenario: SCN-MOD001-070 (MIG · Blocker · negative)
date: 2026-10-05
tier: implementation (NOT a review, NOT a certification, NOT a scenario promotion)
authorization: knowledge/00-System/SCN070-ROUND5-CONVERGENCE-ASSESSMENT-2026-10-05.md — NON_CONVERGING, "persisted strategy-change/root-cause work only"
scenario_status_after: EXECUTED — NOT PROMOTED (unchanged by this record)
---

# SCN-MOD001-070 / GOV-01-R06 — Round-5 root-cause implementation record

This is the implementation-tier record whose absence is round-5 finding
**R5-2**. It covers two things, and it is explicit about which is
directly observed and which is reconciled from other durable evidence:

1. **§3 — this session's own round-5 root-cause work on R5-1.** Directly
   observed and executed here; every command and result in §4 was run in
   this session.
2. **§6 — reconciliation of the round-4 evidence gap.** The round-4
   implementation was produced by a prior ACPX turn that stopped before
   writing its report. **This session did not observe that execution** and
   does not claim to. §6 states only what is independently checkable now
   (bytes, code structure, the watchdog's own contemporaneous observations)
   and labels the rest as reconstruction.

## 1. Why this record exists, and why it is not the filename that was cited

`SCN070-ROUND3-REMEDIATION-2026-10-04.md` cites
`SCN070-ROUND4-ROOT-CAUSE-REMEDIATION-2026-10-04.md` twice (its lines 335
and 397). That file was never written —
`SCN070-ROUND4-ROOTCAUSE-WATCHDOG-CHECKPOINT-2026-10-04.md:3` records why
(the implementing turn *"stopped before a final response or implementation
report"*).

**This record deliberately does not take that filename.** Creating a file
named `…ROUND4-…-2026-10-04.md` on 2026-10-05, from a session that did not
perform round-4's work, would make a dangling citation resolve by
manufacturing a record that misstates its own date and authorship — which
is the R5-2 defect class, not its remedy. Instead: this correctly-dated
round-5 record carries the round-4 reconciliation in §6, and a dated
append-only CORRECTION at the foot of the round-3 record redirects both
dangling citations here.

## 2. Bounded scope, and what this session did not touch

Git HEAD `e481b814a80923849dddfe7a49319112aae7b023`, unchanged. Working tree
uncommitted throughout; **all pre-existing uncommitted work preserved** —
`git status --porcelain` count went 346 → 348, and only upward: +1 for the
§4.4 drill log, +1 for this record. The four files this round *modified*
(§5 items 1-3 and 5) were already in that count. Nothing was reverted,
deleted, or renamed.

- **In scope:** R5-1 (the `os.lstat` unknown-into-absent fold), its negative
  and mutation controls, R5-2 (this record + the round-3 citation
  correction), and R5-3's severity adjudication (§7 — adjudication only).
- **Not touched, deliberately:** every DOM-002 artifact (round 5 remains
  interrupted and non-resumable; not read for verdict, not resumed, not
  dispatched); `SCENARIOS.md`; `REQUIREMENTS.md`; `STATUS.md`;
  `TEST_RESULTS.md`; scenario or requirement status rows of any kind;
  module certification; every other MOD-001 slice; all four governing
  baselines; every `.claude/` file.
- **No reviewer, subagent, or ACPX operation was dispatched.** No sixth
  review was launched, requested, or pre-authorized. No PASS claimed. No
  promotion. No certification. No self-approval.
- **Owner-reserved absolutes respected:** no spend, no paid service, no real
  member data (every fixture synthetic, under `/tmp/scn070r5fix-*`), no
  deploy or Production promotion, no material product/pricing/business/
  architecture/scope change.

## 3. R5-1 — what was changed and why

R5-1 is the fifth appearance of one invariant violation: **an
indeterminate filesystem state classified as a determinate absence.** It
has now been removed from `rglob` (R1-3), `Path.is_dir`/`exists` (R2-3,
R3-1), `main()`'s second probe and `DirEntry` classification (R4-1), and —
here — the `os.lstat` fallback inside `acquire_records_dir`.

Round 4 wrote the outer `os.stat` classification exhaustively but left the
inner fallback as:

```python
    except FileNotFoundError:
        try:
            os.lstat(records_dir)
        except OSError:                                   # ← every error class
            return RecordsPath(RECORDS_PATH_ABSENT, None) # ← asserted as absent
```

So "lstat says the path is not there" and "lstat could not tell me anything
about the path" were the same answer again.

### 3.1 The change: a total classification table, not another shape guard

The four previous fixes were each a guard for the shape that had just been
found, and the fold reappeared at the next site that had no guard. The
strategy this round is to make the classification **total over the syscall
pair**, so there is no residual `OSError` bucket left for an unknown state
to fall into. `acquire_records_dir`'s docstring now carries the table and
the code implements exactly its six rows:

| `os.stat` | `os.lstat` | Kind | Named problem |
|---|---|---|---|
| OK, mode is a directory | not called | `DIRECTORY` | — (proceed to traversal) |
| OK, mode is not a directory | not called | `ERROR` | `RECORDS_PATH_NOT_A_DIRECTORY` |
| `FileNotFoundError` | `FileNotFoundError` | `ABSENT` | — (the ONE permitted vacuous pass) |
| `FileNotFoundError` | returns OK | `ERROR` | `BROKEN_RECORDS_SYMLINK` |
| `FileNotFoundError` | any other `OSError` | `ERROR` | `UNREADABLE_RECORDS_PATH` |
| any other `OSError` | not called | `ERROR` | `UNREADABLE_RECORDS_PATH` |

These rows are total: both calls signal every failure as an `OSError`,
`FileNotFoundError` is the only `OSError` subclass meaning "not there", and
it is handled before the general case in **both** positions.
`RECORDS_PATH_ABSENT` is now reachable by exactly one route — ENOENT from
both calls.

Changed, in `tools/validate_migration_ordering.py`:

* `acquire_records_dir` (the fix): inner `except OSError` split into
  `except FileNotFoundError:` → `ABSENT` and `except OSError as exc:` →
  `ERROR` with a named `UNREADABLE_RECORDS_PATH` problem that says
  *"whether it is genuinely absent or merely unreadable is unknown"*.
* The same function's docstring: the six-row table, plus the bullet list
  corrected to say that absence is established by a *successful ENOENT
  answer from* `lstat`, never by "`lstat` did not succeed".
* The module docstring: R5-1 found it asserting the opposite of the
  code as an absolute (*"`PermissionError` or any other `OSError` is a named
  nonzero diagnostic in both flag modes"*). That sentence is now true, and
  it now names which call establishes which outcome and records that round
  4 left the `lstat` half of it untrue.

### 3.2 Why a structural lock as well as tests

Five rounds of shape-specific behavioral tests did not stop this fold from
relocating. `test_no_except_handler_in_acquire_records_dir_folds_oserror_into_absent`
is therefore decision-level rather than shape-level: it parses the tool's
AST, attributes every `return RECORDS_PATH_ABSENT` to its **innermost**
enclosing `except` handler, and requires that handler's caught type to be
exactly `FileNotFoundError` — and that exactly one such return exists. A
bare `except OSError`, an `except (OSError, ValueError)`, a bare `except:`,
or a sixth site added later all fail it, whichever syscall they sit on.

Round 5 observed that *"a decision-level check that every `except` clause in
`acquire_records_dir` is reached by a test would have found R5-1."* This is
that check, in the form that survives relocation.

One honest limitation: innermost-handler attribution is what makes the lock
correct here (the handlers nest), and the lock reasons about this one
function only. It does not generalise to the rest of the module, and it is
a source-level assertion — §4's behavioral and mutation evidence is what
establishes the runtime property.

## 4. Executed evidence — every command run in this session

Host: uid 501, `Darwin 27.0.0 arm64`, `backend/.venv/bin/python` 3.14.5.

### 4.1 Baseline before any edit (pins the bytes round 5 reviewed)

```
$ git rev-parse HEAD
e481b814a80923849dddfe7a49319112aae7b023

$ shasum -a 256 tools/validate_migration_ordering.py tools/tests/test_validate_migration_ordering.py knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py
8f3d166bd7e647d678b6b5f2ba8ec97be3849c14e6b058d5cbb907a12abb6881  tools/validate_migration_ordering.py
2ad9dc35e9bb6001865eb9603071b206c6fd9343d2911543abf5029c9a410154  tools/tests/test_validate_migration_ordering.py
90b7c3ef0cc030bef2f87f191dc3207d4518f8ac8e1a832fbc24dd8311efc251  knowledge/.../scn070_ordering_lint_mutation_killcheck.py

$ backend/.venv/bin/python -m pytest tools/tests/test_validate_migration_ordering.py -q
55 passed in 0.51s
```

These three values **match the round-5 review report's §1 exactly**, so the
snapshot round 5 reviewed is independently re-pinned here — the specific
gap R5-2 names ("no durable record in the vault pins the bytes this review
examined").

### 4.2 After the fix — tests and mutants

```
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_migration_ordering.py -q
61 passed in 0.59s

$ backend/.venv/bin/python knowledge/.../scn070_ordering_lint_mutation_killcheck.py
m0 baseline (unmutated): SANE — unit exit 0, PASS — 61 of 61 tests passed, 0 skipped
M1 .. M22 : all KILLED
22/22 mutations killed; survivors=[]
exit=0
```

`0 skipped` confirms no live-permission drill silently degraded on this host.

### 4.3 The mutation that proves the old fold is killed — and that it was not covered before

M21 restores R5-1 literally (inner `except FileNotFoundError:` → `except
OSError:`). Run in isolation against a `/tmp` mirror:

```
$ (M21 applied to mirror) python -m pytest tools/tests/test_validate_migration_ordering.py -q
FAILED ... test_asymmetric_lstat_permission_error_is_error_not_absent
FAILED ... test_asymmetric_lstat_eio_is_error_not_absent
FAILED ... test_asymmetric_lstat_eloop_is_error_not_absent
FAILED ... test_no_except_handler_in_acquire_records_dir_folds_oserror_into_absent
4 failed, 57 passed
```

Two results, not one. The mutant is killed by exactly the four controls
written for it — **and the 55 pre-existing tests all pass under it.** That
is direct empirical confirmation of R5-1's central claim: the round-4
battery had *zero* coverage of this branch, which is why 55/55 and 20/20
were green while the defect was live. M22 reintroduces the same fold by the
other available route (classifying lstat's *error* as absent while leaving
the ENOENT handler in place) and is also killed.

### 4.4 Asymmetric fault-injection CLI drill — end to end, pre-fix vs fixed

Full log: `SCN070-R5-1-ASYMMETRIC-INJECTION-DRILL-2026-10-05.txt`.
Fixture: a synthetic records dir holding one genuinely destructive,
genuinely out-of-order `contract` record. PRE-FIX = the M21 mirror (i.e.
round-4 behavior).

| stat/lstat | flag | PRE-FIX | FIXED |
|---|---|---|---|
| ENOENT/EACCES | default | `NOTICE: records dir does not exist` + `PASS` + **exit 0** | `UNREADABLE_RECORDS_PATH`, exit 1 |
| ENOENT/EACCES | `--require-dir` | `MISSING_RECORDS_DIR`, exit 1 | `UNREADABLE_RECORDS_PATH`, exit 1 |
| ENOENT/EIO | default | `NOTICE: … does not exist` + `PASS` + **exit 0** | `UNREADABLE_RECORDS_PATH`, exit 1 |
| ENOENT/EIO | `--require-dir` | `MISSING_RECORDS_DIR`, exit 1 | `UNREADABLE_RECORDS_PATH`, exit 1 |
| ENOENT/ELOOP | default | `NOTICE: … does not exist` + `PASS` + **exit 0** | `UNREADABLE_RECORDS_PATH`, exit 1 |
| ENOENT/ELOOP | `--require-dir` | `MISSING_RECORDS_DIR`, exit 1 | `UNREADABLE_RECORDS_PATH`, exit 1 |
| ENOENT/ENOENT | default | `NOTICE: … does not exist` + `PASS` + exit 0 | **unchanged** — genuine absence |
| ENOENT/ENOENT | `--require-dir` | `MISSING_RECORDS_DIR`, exit 1 | **unchanged** |
| ENOENT/lstat OK | both | `BROKEN_RECORDS_SYMLINK`, exit 1 | **unchanged** |

The three indeterminate rows flip from a false clean pass to a named
nonzero error in **both** flag modes, including the `--require-dir`
"right exit code, wrong reason" sub-defect round 4 recorded under R4-1. The
two legitimate rows are byte-identical — the fix **discriminates** rather
than rejecting everything, which is the control that stops the three rows
above from passing for a trivial reason.

### 4.5 Type, lint, and no-regression checks

```
$ backend/.venv/bin/python -m mypy tools/validate_migration_ordering.py
Success: no issues found in 1 source file

$ backend/.venv/bin/python -m ruff check tools/validate_migration_ordering.py tools/tests/test_validate_migration_ordering.py
Found 4 errors.        # 2× EXE001, 2× FLY002 — the SAME four as round 4; none added here

$ backend/.venv/bin/python tools/validate_migration_ordering.py      # the automated caller's invocation
NOTICE: records dir exists but contains no migration records — vacuous pass…
PASS …
exit=0                 # unchanged against the real in-repo tree
```

ruff's 4 diagnostics are round-5 **R5-9**, still unadjudicated; this round
neither fixed nor worsened them, and recording that is not adjudicating
them.

### 4.6 Post-change bytes

```
86aad0755c51684eb99d50dd332738e5e316836ca23f9cf1fa6360e0a7336639  tools/validate_migration_ordering.py
708ac1d986a1c258c076d163b19bf4d0054f1faf927f8c309bb3d2d12dff955c  tools/tests/test_validate_migration_ordering.py
7100e7ef50e8c7982ec5a95722b18a5a1ee744ec94a57583c302fa93a4177eb6  knowledge/.../scn070_ordering_lint_mutation_killcheck.py
```

## 5. Files this round touched — exactly six

1. `tools/validate_migration_ordering.py` — the R5-1 fix + the two
   docstrings. SHA-256 above.
2. `tools/tests/test_validate_migration_ordering.py` — `_with_asymmetric_injected_stat`,
   five asymmetric behavioral tests, one structural lock. SHA-256 above.
3. `knowledge/.../scn070_ordering_lint_mutation_killcheck.py` — mutants M21,
   M22. SHA-256 above.
4. `knowledge/.../SCN070-R5-1-ASYMMETRIC-INJECTION-DRILL-2026-10-05.txt` — new, the §4.4 log.
5. `knowledge/.../SCN070-ROUND3-REMEDIATION-2026-10-04.md` — dated
   append-only CORRECTION at the foot only; no prior text altered or
   removed. That file is **untracked** (`?? ` in porcelain), so `git diff`
   cannot evidence this; the actual verification is line count 449 → 496
   with the two cited lines re-read intact in place (`sed -n '335p;397p'`
   still returns both original citations verbatim).
6. This record — new.

No deletions, no renames, no commit, push, stash, reset, checkout, discard,
or branch change.

## 6. Reconciliation of the round-4 evidence gap (R5-2)

**What this session directly observed:** the bytes. `8f3d166b…` /
`2ad9dc35…` / `90b7c3ef…` were the working-tree state at this session's
start (§4.1), they match the round-5 review's §1 exactly, and they are
therefore now pinned by a durable implementation-tier record for the first
time. That is the substantive half of R5-2 and it is closed by direct
observation.

**What is reconstruction, not observation.** This session did not watch
round 4 execute and cannot attest to it. What is checkable now:

* `SCN070-ROUND4-ROOTCAUSE-WATCHDOG-CHECKPOINT-2026-10-04.md` records the
  orchestrator's own contemporaneous re-execution after the ACPX turn
  stopped: 55 passed, 20/20 mutants killed, mypy PASS, `verify_baselines.py`
  4/4 MATCH, `git diff --check` clean, ruff 4 diagnostics left
  unadjudicated. That document correctly labels itself *"not an independent
  review or scenario PASS"* and asserts no file hashes.
* The round-4 changes themselves are legible in the code: the tri-state
  `acquire_records_dir`, `ValidationOutcome` carrying problems and notice
  together, `main()` consuming that one result, `TreeEntry`'s captured
  `DirEntry` metadata. The round-5 review independently re-verified their
  *behavior* (its §5.1 closes R4-1 on its named shape at two ancestor
  depths in both flag modes).
* The raw ACPX captures (`SCN070-ROUND4-ROOTCAUSE-ACPX-RAW-…`,
  `…-RETRY-RAW-…`, `…-EXIT-…json`) are the only trace of the implementing
  turn's own reasoning.

**What remains irrecoverable, and is not papered over.** No record states
what round 4 *intended* to leave open. The limitation list every prior
round carried forward (the R2-4 residual, R3-2, R3-3, R3-4, mutation-anchor
coupling, "mutation score is not a scenario PASS") has no round-4
successor written by its own author; §8 below reconstructs it from the
round-4 and round-5 review reports, which is weaker evidence than an
author's own statement and is labelled as such. R5-2's structural
complaint is closed; the historical gap in round-4's authorial intent
cannot be, and no later session should represent §8 as round 4's own
limitation list.

**Stale hashes in the round-3 record are not a defect.** That record's
`5738c951…` / `10c2872b…` / `7aa1a487…` correctly describe *its own*
round's bytes under this project's append-not-rewrite convention. They are
superseded, not wrong.

## 7. R5-3 (FIFO hang) — severity adjudication against scope

Round 5 rated this **P3** and asked for separate adjudication before any
claim that the lint gate is complete. Adjudicated here; **not fixed** — the
authorized work is bounded to R5-1, R5-2 and this adjudication, and P3
remediation is outside it.

**Reproduced in this session:**

```
$ mkfifo $D/records/0001_fifo.yaml
$ timeout 15 backend/.venv/bin/python tools/validate_migration_ordering.py --records-dir $D/records
exit=124          # killed by timeout; NO output at all, no verdict
```

A FIFO named `*.yaml` directly inside the records dir is classified as a
record (`:400-403`) and `parse_front_matter`'s `path.read_text` (`:215`)
blocks forever on a writer-less FIFO.

**Reachability, bounded by evidence:**

* The only automated caller is `knowledge/05-QA/tools/run_regression.py:62`,
  which passes **no** `--records-dir`, so it targets
  `backend/migrations/records/`.
* That directory is git-tracked and holds exactly one entry:
  `.gitkeep`, mode `100644` (`git ls-files -s`).
* **Git's index cannot represent a FIFO** — only `100644`/`100755`
  regular files, `120000` symlinks, `160000` gitlinks. A FIFO therefore
  cannot enter that tree by clone, checkout, merge, or pull.
* `.github/workflows` does not exist, so there is no unattended runner
  today (this is R3-4, an open GOV-01-R04 obligation).

So reaching it requires local write access to the working tree plus a
deliberate `mkfifo` in that specific directory. There is no
repository-mediated or remote path to it.

**Adjudication: P3 is correct at current scope, with a recorded conditional
escalation.**

* It is **not a fail-open.** No `PASS`, no exit 0, no notice, no false
  absence is ever produced, so invariant I-1 is untouched. This is the
  property that keeps it out of P2 — unlike R5-1, which this record fixed.
* It is also **not fail-closed** in the ordinary sense: it is *no verdict*.
  For a blocking gate that is still safe by default (no verdict cannot be
  read as a pass, so nothing merges on it), which is why it is not P2. The
  harm is availability and operator experience, not correctness.
* **Conditional escalation, recorded now so it is not lost:** the moment
  CI wiring lands (R3-4), this should be re-rated at least P2 and fixed
  first. An unattended job would hang rather than fail, holding a runner
  until job timeout with no diagnostic — qualitatively worse than the
  R5-4 class, which at least terminates nonzero with a traceback. The fix
  is a regular-file check before `read_text`, which would also give
  R5-4's three shapes a named problem instead of a raw traceback.
* **This record does not claim the lint gate is complete.** R5-3, R5-4
  through R5-9, and round-4's R4-6 all remain open and unadjudicated except
  where stated here.

## 8. Limitations — reconstructed carry-forward, plus this round's own

Items 1-6 are reconstructed from the round-4 and round-5 **review** reports,
not from a round-4 implementation record (see §6); they should be read as
this session's reading of those reviews, not as round 4's own statement.

1. **R5-4 / R2-4 / R4-3 residual** — unreadable, non-UTF-8, and non-regular
   individual record files produce raw tracebacks outside the tool's named
   vocabulary. Nonzero, so fail-closed; unnamed, so poor diagnostics.
2. **R5-3** — the FIFO hang, adjudicated in §7, open.
3. **R5-5** — two round-3 live drills still skip by bare `return` rather
   than a reported skip. Both genuinely executed on this host (`0 skipped`).
4. **R5-6** — a test docstring still names a `sitecustomize`-free wrapper
   mechanism it does not use.
5. **R5-7** — the AST structural lock's banned set (`Path.exists/is_dir/
   is_file/is_symlink`) is narrower than its stated rationale; it omits
   `os.path.isdir`, `os.path.lexists`, `os.path.islink`, `glob`/`rglob`.
   Round 5 demonstrated a class-evading reintroduction that the lock did
   not fire on (though five behavioral tests killed it). **Not addressed
   this round** — out of the authorized bounds — and it applies to the
   *new* lock in §3.2 as well, which bans a fold by caught-type rather
   than enumerating stdlib families.
6. **R5-8** (`OUT_OF_ORDER_PHASE` wording wrong for a phase regression) and
   **R5-9** (4 unadjudicated ruff diagnostics) — open, untouched.
7. **R4-6** — the `SCENARIOS.md` stale execution-evidence pointer. Round 5
   excluded it by charter and this session did not touch `SCENARIOS.md`, so
   it remains open and unadjudicated.
8. **A mutation score is not a scenario PASS, and 22/22 is not invariant
   coverage.** Round 5 proved this against the round-4 battery: 55/55 and
   20/20 were green while R5-1 was live. The same caveat binds this
   round's 61/61 and 22/22 — the mutants are enumerated from the fixes that
   were written, so they say nothing about a defect outside the set. §3.2's
   decision-level lock and §4.4's end-to-end drill are the partial answer
   to that, not a refutation of it.
9. **R5-1's residual reachability claim is inherited, not re-proven.**
   Round 5 reported "race-only" as *"a reasoned conclusion from a bounded
   search, not an exhaustive proof."* This session did not repeat that
   search and does not strengthen the claim. It is now moot for
   correctness — the branch fails closed either way — but it remains the
   reason R5-1 was calibrated P2 rather than P1.
10. **Injection is not the filesystem.** §4.4's evidence comes from
    patching `os.stat`/`os.lstat`, which is how an inter-syscall race
    becomes deterministic. It is not proof that a real filesystem produces
    that pair; it is proof that the tool classifies it correctly if one
    does.
11. **No independent review of this snapshot exists.** Everything in §4 is
    self-executed implementation evidence. The five-review absolute cap is
    reached; this record neither requests nor authorizes a sixth.

## 9. Status after this record

- **SCN-MOD001-070: `EXECUTED — NOT PROMOTED`.** Unchanged. No scenario
  status row was read for verdict or written.
- **R5-1: fixed and controlled** by 5 behavioral tests, 1 structural lock,
  2 mutants, and an end-to-end before/after drill — all self-executed.
  Whether that closes the finding is an independent-assurance judgment this
  record cannot make for itself.
- **R5-2: structurally closed** — the reviewed bytes are pinned (§4.1), an
  implementation-tier record exists, and the round-3 citations are
  corrected. The irrecoverable part (round 4's own authorial intent) is
  named in §6 rather than reconstructed silently.
- **R5-3: adjudicated P3** at current scope with a conditional escalation
  to ≥P2 on CI wiring (§7). Not fixed.
- **R5-4 … R5-9, R4-6: open.** No PASS is claimed for the lint gate.
- **Convergence: `NON_CONVERGING`,** unchanged by this record. No sixth
  ordinary review, replacement, or reassurance review is authorized by
  anything here.

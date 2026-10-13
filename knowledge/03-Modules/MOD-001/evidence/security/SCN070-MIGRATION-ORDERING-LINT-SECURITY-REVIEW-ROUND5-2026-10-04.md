---
doc: SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND5
module: MOD-001
requirement: GOV-01-R06 (Database-change policy/tooling), TSD §24.2
scenario: SCN-MOD001-070 (MIG · Blocker · negative)
round: 5 (exceptional, authorized by AUTONOMOUS_CONVERGENCE_STATE.json `scn070WorkUnitState.fifthReviewDecision`)
date: 2026-10-04
verdict: BLOCKED
counts: P0=0 / P1=0 / P2=2 / P3=6
---

# SCN-MOD001-070 / GOV-01-R06 — Independent Security & Scenario Review, Round 5

## 1. Independence and integrity

Fresh-context reviewer. I did not author, and have not previously reviewed,
any artifact under review — no self-approval. I was READ-ONLY on
implementation: no tool, test, record, scenario status, `TEST_RESULTS.md`,
`STATUS.md`, `CURRENT_STATE.md`, convergence ledger, or
`REVIEW_IN_FLIGHT.md` was modified. The only file this session created in the
repository is this report. All fixtures were built under `/tmp/scn070r5*`
(synthetic records only — no real member data, no spend, no paid service, no
deploy). No subagent or further reviewer was dispatched. Every claim below
was executed in this session; no prior round's verdict was accepted on its
text.

Reviewed bytes, pinned here because **no durable record currently pins them**
(see R5-2):

```
$ git rev-parse HEAD
e481b814a80923849dddfe7a49319112aae7b023

$ shasum -a 256 tools/validate_migration_ordering.py tools/tests/test_validate_migration_ordering.py knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py
8f3d166bd7e647d678b6b5f2ba8ec97be3849c14e6b058d5cbb907a12abb6881  tools/validate_migration_ordering.py
2ad9dc35e9bb6001865eb9603071b206c6fd9343d2911543abf5029c9a410154  tools/tests/test_validate_migration_ordering.py
90b7c3ef0cc030bef2f87f191dc3207d4518f8ac8e1a832fbc24dd8311efc251  knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py
```

Host: uid 501, macOS/APFS, `backend/.venv/bin/python` 3.14.5. Mode 000 is
enforced on this host (proven by the live drills below actually failing
closed rather than skipping), so no live-permission drill silently degraded.

## 2. Scope, and what I deliberately excluded

In scope, exactly as tasked:

1. `tools/validate_migration_ordering.py` — the tri-state records-path
   metadata acquisition shared by traversal and the CLI notice path, and the
   one-result CLI notice behavior.
2. `tools/tests/test_validate_migration_ordering.py` — the tests covering
   the above.
3. `knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py`
   and its evidence.
4. `knowledge/03-Modules/MOD-001/evidence/implementation/SCN070-ROUND3-REMEDIATION-2026-10-04.md`
   — the accuracy correction to the previously false fail-closed claim.

**Deliberately excluded: DOM-002 and every `DOM002-*` artifact.** Its round-5
review is interrupted and non-resumable, and reviewing it is prohibited by
this review's charter. I did not open, read for verdict, resume, or dispatch
any DOM-002 artifact. Also excluded: every other MOD-001 slice, every other
gate, module certification, and scenario/requirement status rows (I did not
read them for verdict and did not change them). I ran no broad or unrelated
test suite; execution was bounded to the scoped files plus `mypy`/`ruff` on
the two scoped source files.

## 3. The invariant under test

> **I-1 (central).** No inaccessible, indeterminate, or error state of the
> records path may produce a PASS, a clean exit, or a benign/informational
> NOTICE. Only a state the tool *actually determined* to be "genuinely
> absent" or "determined and clean" may do so.

> **I-2.** A verdict and the diagnostic printed beside it must derive from
> one authoritative evaluation; a notice may never contradict the verdict or
> assert a fact about a path the tool did not establish.

> **I-3.** The tool never creates, modifies, chmods, or deletes anything in
> the checked tree.

> **I-4 (evidence discipline, DC-10).** A durable record may not assert a
> safety property it did not execute, and may not cite evidence that does
> not exist.

## 4. Executed baseline — tests, mutants, type/lint

```
$ backend/.venv/bin/python -m pytest tools/tests/test_validate_migration_ordering.py -q
.......................................................                  [100%]
55 passed in 0.59s
```

```
$ backend/.venv/bin/python knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py
m0 baseline (unmutated): SANE — unit exit 0, PASS — 55 of 55 tests passed, 0 skipped (discovered dynamically, not hand-listed).
M1 .. M20 : all KILLED
real tool sha256 unchanged:  8f3d166bd7e647d678b6b5f2ba8ec97be3849c14e6b058d5cbb907a12abb6881
real test sha256 unchanged:  2ad9dc35e9bb6001865eb9603071b206c6fd9343d2911543abf5029c9a410154
20/20 mutations killed; survivors=[]
round-1 survivors now killed: ['M3 start-phase guard neutralized (R1-1, SURVIVED at round 1)', 'M5 main() rejection exit code neutralized (R1-2, SURVIVED at round 1)']
```

55/55 and 20/20 both reproduce independently, and the `0 skipped` line
confirms no live drill degraded on this host. `mypy` PASS
(`Success: no issues found in 1 source file`). `ruff check` on the two scoped
files: **4 errors** (2× `EXE001`, 2× `FLY002`) — see P3 R5-9.

## 5. Decisive discriminating cases — executed

### 5.1 Unreadable ancestor of the records path (the R4-1 shape) — CLOSED

Fixture: `/tmp/scn070r5/a/parent/records/0001_destructive_contract.yaml`,
a lone genuinely destructive, genuinely out-of-order `contract`; `parent`
chmod 000; the records dir itself readable in its own right.

```
$ backend/.venv/bin/python tools/validate_migration_ordering.py --records-dir /tmp/scn070r5/a/parent/records
BLOCKED: 1 problem(s) found:
  - /tmp/scn070r5/a/parent/records: UNREADABLE_RECORDS_PATH — could not read this path's metadata (Permission denied), so whether it holds migration records is unknown; an unreadable path must never report a pass, with or without --require-dir
exit=1

$ ... --records-dir /tmp/scn070r5/a/parent/records --require-dir
(identical UNREADABLE_RECORDS_PATH problem)
exit=1

$ chmod 700 parent; ... --records-dir /tmp/scn070r5/a/parent/records     # discriminating control
BLOCKED: 1 problem(s) found:
  - 0001_destructive_contract.yaml: OUT_OF_ORDER_PHASE — change_id 'drop_members_table' starts at 'contract' but must start with 'expand'
exit=1

$ ... --records-dir /tmp/scn070r5/a2/gp/parent/records                   # grandparent mode 000
  - ...: UNREADABLE_RECORDS_PATH — ... (Permission denied) ...
exit=1
```

**I-1 and I-2 upheld on this shape, in both flag modes, at any ancestor
depth, with the readable counterpart discriminating.** No `PASS`, no
`NOTICE`, no false "does not exist". Round-4's R4-1 — the fail-open that
produced exit 0 plus a NOTICE asserting absence over this exact tree — is
**closed**, anchored at `tools/validate_migration_ordering.py:447-466`
(`acquire_records_dir`) and `:553-587` (`main()` printing only
`outcome.notice`).

R3-1's older named shape (mode-000 records **root**) also still fails closed:
`/tmp/scn070r5/h/root000: UNREADABLE_RECORDS_PATH — could not enumerate this
directory (Permission denied)`, exit 1 — no regression from the acquisition
rewrite (stat succeeds on a mode-000 directory, so the shape correctly falls
through to `enumerate_tree`'s own guard at `:322-335`).

### 5.2 Fault-injected metadata errors — one residual fold found

I intercepted `os.stat` and `os.lstat` for one target path only, delegating
all other paths to the real implementation, and inspected
`validate_directory` in both flag modes plus `run_validation().notice`
(`/tmp/scn070r5/inject_probe.py`, not committed).

| stat raises | lstat raises | default verdict | notice | I-1 |
|---|---|---|---|---|
| `PermissionError` EACCES | EACCES | exit 1, `UNREADABLE_RECORDS_PATH` | None | upheld |
| `OSError` EACCES | EACCES | exit 1, `UNREADABLE_RECORDS_PATH` | None | upheld |
| `OSError` ELOOP | ELOOP | exit 1, `UNREADABLE_RECORDS_PATH` (Too many levels of symbolic links) | None | upheld |
| `OSError` EIO | EIO | exit 1, `UNREADABLE_RECORDS_PATH` (Input/output error) | None | upheld |
| `FileNotFoundError` | ENOENT | exit 0 PASS; `--require-dir` → `MISSING_RECORDS_DIR` | absent-notice | upheld (genuine absence) |
| `FileNotFoundError` | lstat OK | exit 1, `BROKEN_RECORDS_SYMLINK` | None | upheld |
| **`FileNotFoundError`** | **`PermissionError` EACCES** | **exit 0, PASS** | **"records dir does not exist"** | **VIOLATED** |
| **`FileNotFoundError`** | **`OSError` EIO** | **exit 0, PASS** | **"records dir does not exist"** | **VIOLATED** |
| **`FileNotFoundError`** | **`OSError` ELOOP** | **exit 0, PASS** | **"records dir does not exist"** | **VIOLATED** |

This is finding **R5-1** (§7). The stat-vs-lstat *choice* is otherwise
correct: `os.stat` (follow) is what keeps a symlinked records dir usable, and
`os.lstat` is the right second probe for distinguishing a dangling symlink —
confirmed by independent mutant MUT-R5-B (§6).

### 5.3 Genuine absence, wrong-type paths, symlinks

```
c1 absent, default        -> exit 0, PASS + "records dir does not exist" notice   (documented vacuous pass)
c2 absent, --require-dir  -> exit 1, MISSING_RECORDS_DIR
d1 regular file           -> exit 1, RECORDS_PATH_NOT_A_DIRECTORY
d2 FIFO                   -> exit 1, RECORDS_PATH_NOT_A_DIRECTORY
d3 unix socket            -> exit 1, RECORDS_PATH_NOT_A_DIRECTORY
d4 path UNDER a file      -> exit 1, UNREADABLE_RECORDS_PATH (Not a directory)   [ENOTDIR is not absence]
d5 /dev/null              -> exit 1, RECORDS_PATH_NOT_A_DIRECTORY
e1 symlink -> valid dir holding destructive record  -> exit 1, OUT_OF_ORDER_PHASE  (usable through the link)
e2 symlink -> missing target, default               -> exit 1, BROKEN_RECORDS_SYMLINK
e3 same, --require-dir                              -> exit 1, BROKEN_RECORDS_SYMLINK
e4 symlink loop                                     -> exit 1, UNREADABLE_RECORDS_PATH (ELOOP), terminated immediately
e5 symlink whose target ancestor is mode 000        -> exit 1, UNREADABLE_RECORDS_PATH (EACCES)
e6 symlinked subdir inside the tree hiding a destructive contract -> exit 1, q4: SYMLINK_IN_RECORDS_TREE
```

**I-1 upheld on every one of these.** The only exit-0 PASS in the whole
matrix is the genuinely-absent case the requirement documents, and it fails
closed under `--require-dir`.

### 5.4 Read-only non-mutation (I-3) — verified by inventory, not assertion

Fixture tree with records, a nested subdir, `.gitkeep`, and a relative
symlink, then `chmod -R a-w`. Full inventory (`name|mode|mtime|size|inode`
for every path, sorted) captured before and after two runs (default and
`--require-dir`):

```
--- inventory diff (names|modes|mtimes|sizes|inodes) ---
IDENTICAL — no create/modify/chmod/delete
```

**I-3 upheld.** The runs themselves exited 1 naming `0009_link.yaml:
SYMLINK_IN_RECORDS_TREE` and `sub/0003_nested.yaml:
UNRECOGNIZED_RECORD_FILE`, so the tree was genuinely traversed rather than
rejected early.

### 5.5 Record-file-level shapes

```
f1 unreadable individual record file  -> raw PermissionError traceback, exit 1      (unnamed; fail-closed)
f2 non-UTF-8 record file              -> raw UnicodeDecodeError traceback, exit 1   (unnamed; fail-closed)
f3 FIFO named *.yaml INSIDE records   -> HANGS; killed by timeout after 15s (exit 124) — NO verdict ever
f4 unix socket named *.yaml INSIDE    -> raw OSError ENOTSUP traceback, exit 1      (unnamed; fail-closed)
```

f1/f2/f4 are the carried R2-4/R4-3 residual, unchanged, and are nonzero so
they do not violate I-1. f3 is new and is the one shape in the catalogue that
produces *no* verdict at all — see P3 R5-3.

## 6. Independent mutants (mine, on throwaway `/tmp` mirrors)

| Mutant | Change | Result |
|---|---|---|
| m0 | unmutated mirror | 55 passed — baseline sane |
| **MUT-R5-A** | reintroduce the R4-1 root cause using `os.path.isdir` / `os.path.lexists` instead of pathlib, i.e. a *class-evading* reversion the AST structural lock does not ban | **8 failed, 47 passed** — killed by `test_injected_permission_error_...`, `test_injected_non_permission_oserror_...`, `test_records_path_under_a_regular_file_...`, `test_cli_unreadable_parent_...`, `test_notice_is_never_returned_alongside_problems` |
| **MUT-R5-B** | `os.stat(records_dir)` → `os.lstat(records_dir)` in `acquire_records_dir` (the stat-vs-lstat choice) | **3 failed, 52 passed** — killed by `test_symlink_to_a_real_records_dir_is_still_usable`, `test_broken_symlink_records_dir_...`, `test_acquire_records_dir_is_tri_state_on_real_paths` |

MUT-R5-A is the important one: it proves the **behavioral** layer, not just
the source-level AST lock, kills a reintroduction of the root cause through a
different stdlib family. That is a genuine strengthening over rounds 1-4,
where each fix was pinned by shape-specific tests only. Repo hashes
re-verified unchanged after both drills.

## 7. Findings

### R5-1 — P2 — Residual "unknown folded into absent" in the lstat fallback; module docstring states the opposite as an absolute

**Invariant violated: I-1 (and I-4, in the code's own documentation).**

Anchor: `tools/validate_migration_ordering.py:449-453`

```python
    except FileNotFoundError:
        try:
            os.lstat(records_dir)
        except OSError:
            return RecordsPath(RECORDS_PATH_ABSENT, None)
```

The `except OSError` here catches **every** error class, so "lstat says the
path is not there" and "lstat could not tell me anything about the path" are
again the same answer — the exact fold this scenario has now spent five
rounds eliminating at four other sites (`rglob` → `Path.is_dir`/`exists` →
`main()`'s second probe → `DirEntry` classification). Executed evidence
(§5.2, `/tmp/scn070r5/inject_probe.py`): with `os.stat` raising
`FileNotFoundError` and `os.lstat` raising `PermissionError`, `OSError(EIO)`,
or `OSError(ELOOP)`, the tool returns `problems == []`, **exit 0**, the
ordinary `PASS` line, and
`NOTICE: records dir does not exist — vacuous pass, no record was checked` —
an affirmative statement of absence about a path whose state was never
determined. With `--require-dir` the exit is 1 but the named reason is
`MISSING_RECORDS_DIR` ("does not exist"), which is the "right exit code,
wrong reason" sub-defect round 4 recorded as part of R4-1.

The same lines make two in-code claims false in the reassuring direction —
the R4-2 failure mode, relocated from the evidence record into the tool:

* `tools/validate_migration_ordering.py:95-98` (module docstring): *"Only a
  genuine `FileNotFoundError` on a path that is not even a symlink may
  produce the documented default vacuous PASS; `PermissionError` or any other
  `OSError` is a named nonzero diagnostic **in both flag modes**."* Executed
  counterexample above: a `PermissionError` from `lstat` produces the default
  vacuous PASS.
* `tools/validate_migration_ordering.py:429-431` and `:436-441`
  (`acquire_records_dir` docstring): the first bullet describes the absent
  branch as *"`FileNotFoundError` on a path that is not even a symlink"*,
  but the implemented test for "not even a symlink" is "lstat raised any
  `OSError`", which is a strictly weaker condition; the third bullet states
  *"any other `OSError` … Named, nonzero, both flag modes"* without the
  lstat-path exception.

Test-coverage gap at the same seam, cited precisely:
`tools/tests/test_validate_migration_ordering.py:934` defines
`_with_injected_stat(target, exc, also_lstat: bool = True)` — the parameter
exists specifically to allow asymmetric injection, and **is never once called
with `also_lstat=False`** (the only three call sites are `:961`, `:978`,
`:997`, all symmetric). So all three injection tests give `stat` and `lstat`
the *same* exception, and the asymmetric branch has zero coverage. The
20-mutant battery likewise has no mutant on these lines: M15 mutates the
outer `except OSError`, M19 mutates the `BROKEN_RECORDS_SYMLINK` return, and
neither touches the inner `except OSError: return ABSENT`.

**Why P2 and not P1, stated openly so governance can overrule me.** The
charge pre-classifies "a clean exit or benign notice on a path whose state
could not be determined" as P0/P1-class, and on the letter of that this is
P1. I am recording P2 on reachability alone: `stat` and `lstat` resolve all
ancestor components identically, so no *static* filesystem shape produces
ENOENT-from-stat with non-ENOENT-from-lstat — I searched for one (unreadable
ancestor at both depths, symlink loop, ENOTDIR, broken link, link through an
unreadable ancestor; §5.1/§5.3 all route to the correct named branch). It
requires a mutation of the path between two consecutive syscalls, and the
only automated caller (`knowledge/05-QA/tools/run_regression.py:61-62`) runs
against an in-repo path with no adversary. Round 4 calibrated a *statically*
reachable instance of this identical fold at P2, so calling a race-only
instance P1 would be inconsistent with the slice's own calibration. The
remedy is two lines (`except FileNotFoundError: return ABSENT` / `except
OSError as exc: return ERROR(...)`) plus one asymmetric-injection test, so
the cost of closing it is not the reason to down-rate it.

### R5-2 — P2 — The round-4 remediation has no implementation record, and the round-3 correction cites a file that does not exist

**Invariant violated: I-4 (DC-10 evidence over assertion; DC-15 durable
memory).**

The accuracy correction appended to
`SCN070-ROUND3-REMEDIATION-2026-10-04.md` is itself **technically accurate**
(adjudicated in §8). But it cites its backing evidence twice —
`SCN070-ROUND4-ROOT-CAUSE-REMEDIATION-2026-10-04.md`, at that record's
line 335 (*"This session independently re-reproduced that same output before
fixing it (see … §3)"*) and line 397 (*"which is recorded in …"*). That file
does not exist:

```
$ ls knowledge/03-Modules/MOD-001/evidence/implementation/ | grep -i SCN070-ROUND4
SCN070-ROUND4-ROOTCAUSE-ACPX-EXIT-2026-10-04.json
SCN070-ROUND4-ROOTCAUSE-ACPX-RAW-2026-10-04.txt
SCN070-ROUND4-ROOTCAUSE-ACPX-RETRY-RAW-2026-10-04.txt
SCN070-ROUND4-ROOTCAUSE-WATCHDOG-CHECKPOINT-2026-10-04.md

$ find . -name "SCN070-ROUND4-ROOT-CAUSE-REMEDIATION*"
(no output)
```

`SCN070-ROUND4-ROOTCAUSE-WATCHDOG-CHECKPOINT-2026-10-04.md:3` explains why —
the implementing ACPX turn *"stopped before a final response or
implementation report."* The consequence is structural, not cosmetic:

* There is **no implementation-tier record** for the change actually under
  review — nothing durable states what was changed and why, what was
  executed, what was deliberately left open, or which bytes were produced.
  The watchdog checkpoint is an orchestrator observation (and correctly
  labels itself *"not an independent review or scenario PASS"*); it asserts
  no file hashes at all.
* `SCN070-ROUND3-REMEDIATION-2026-10-04.md:410-412` still asserts
  `5738c951…` / `10c2872b…` / `7aa1a487…` as the three files' SHA-256. All
  three are now **stale** (actual: `8f3d166b…` / `2ad9dc35…` / `90b7c3ef…`).
  Within this project's append-not-rewrite convention that record is
  correctly describing its own round's bytes — but combined with the missing
  round-4 report, the net effect is that **no durable record in the vault
  pins the bytes this review examined.** §1 of this report is the first.
* The limitations list that every prior round carried (R2-4 residual, R3-2,
  R3-3, R3-4, mutation-anchor coupling, "mutation score is not a scenario
  PASS") has no round-4 successor, so the carried-forward P3 set exists only
  in review reports, not in an implementation record.

The underlying *facts* the dangling citation vouches for are true and I
re-established them independently (§5.1 reproduces the fix; §8 confirms the
correction's technical claim), so this is an evidence-trail defect rather
than a false claim. It is nonetheless the same class round 4 rated P2, and it
is the one place a governance reader would go to verify that the round-4
strategy was executed as authorized.

### R5-3 — P3 — A FIFO named `*.yaml` inside the records dir hangs the lint indefinitely (no verdict)

`tools/validate_migration_ordering.py:215` (`parse_front_matter`'s
`path.read_text`) opens a record file with no type check. A FIFO directly
inside the records dir is classified as a record (`:400-403`: not a symlink,
not a dir, suffix `.yaml`, parent matches) and `open()` blocks forever on a
writer-less FIFO:

```
f3 FIFO named *.yaml INSIDE records dir  -> timeout 15 ... ; exit=124 (killed, no output)
```

This does not violate I-1 — no PASS and no notice is produced — but it is the
only catalogued shape that yields **no verdict at all** rather than a nonzero
one, so an unattended gate would hang rather than fail. Qualitatively
distinct from the R4-3 residual class (which terminates nonzero). The
same one-line widening that would name R5-4 does not fix this; it needs a
regular-file check before `read_text`.

### R5-4 — P3 — Unnamed tracebacks on unreadable / non-UTF-8 / non-regular record files (R4-3, carried, unchanged)

`tools/validate_migration_ordering.py:215`. Executed: mode-000 record file →
raw `PermissionError`, exit 1; non-UTF-8 record → raw `UnicodeDecodeError`,
exit 1; unix socket named `*.yaml` → raw `OSError` ENOTSUP, exit 1. All
nonzero, therefore fail-closed and not an I-1 violation; all outside the
tool's named-problem vocabulary. No regression against round 4; the socket
case is one more member of the same class, as the mid-traversal
`FileNotFoundError` was at round 4.

### R5-5 — P3 — The two round-3 live drills still skip by bare `return` (R4-4, carried, acknowledged)

`tools/tests/test_validate_migration_ordering.py:677-700` and `:703-721` use
`return` rather than a reported skip when the host does not enforce mode 000;
on such a host they report PASSED with no assertion executed. The round-4
work added a proper `_skip()` helper (`:801-813`) and used it for the five
new live drills, and deliberately left these two — which the test file states
in-line at `:809-810`. On this host both genuinely ran (`0 skipped` in §4).
Reporting hygiene only.

### R5-6 — P3 — Docstring describes a mechanism the test does not use (R4-5, carried verbatim)

`tools/tests/test_validate_migration_ordering.py:678-679` still opens
*"driven by an injected failure via a sitecustomize-free wrapper"* and then
states it uses the live `chmod` mechanism. Unchanged from round 4.

### R5-7 — P3 — The AST structural lock's banned set is narrower than its stated rationale

`tools/tests/test_validate_migration_ordering.py:1259-1298` bans
`Path.exists/is_dir/is_file/is_symlink` by attribute name. Its docstring
justifies this as banning the *class* of calls that "return False on OSError
instead of raising", but the set omits `os.path.isdir`, `os.path.lexists`,
`os.path.islink`, and `glob`/`rglob` — all members of that class.
Demonstrated: my MUT-R5-A reintroduced the R4-1 root cause using
`os.path.isdir`/`os.path.lexists` and the AST lock did **not** fire. It was
nevertheless killed by five behavioral tests (§6), so this is
completeness-of-the-lock, not a live hole — but the lock is presented as what
makes the fix "irreversible-in-one-line" (`:792-794`), and on the evidence it
is the behavioral layer that actually does that work.

### R5-8 — P3 — `OUT_OF_ORDER_PHASE` message is wrong for a phase *regression*

`tools/validate_migration_ordering.py:280-284`. When a change_id's phase
moves backwards (e.g. `switch` then `expand`), `needed = PHASE_ORDER[last]`
and the message reads *"jumps to 'expand' without a preceding 'switch'"* —
describing a skip-ahead when the actual fault is a regression. The record is
still reported and the run still exits 1, so fail-closed holds; diagnostic
wording only.

### R5-9 — P3 — `ruff` diagnostics on the two scoped files remain unadjudicated (DC-12)

`backend/.venv/bin/python -m ruff check` on the two scoped files reports
**4 errors**: 2× `EXE001` (shebang present, file not executable, on the tool
and the test) and 2× `FLY002` (static `str.join` that should be an f-string,
in the test). The round-4 watchdog checkpoint recorded these and explicitly
left their *"disposition … not adjudicated"*; they remain unadjudicated. No
functional impact; DC-12 clean-code hygiene.

## 8. Is the SCN070-ROUND3-REMEDIATION accuracy correction now accurate?

**The correction's technical claim is accurate, verified by execution.
There is no residual overclaim in the corrected text itself. The residual
problem is its citation, not its content** (R5-2).

The correction block at
`SCN070-ROUND3-REMEDIATION-2026-10-04.md:321-345` replaces the original §7
item-1 assertion — *"the tool dies with a traceback — fail-closed (nonzero),
not fail-open"* — with: *"`Path.is_dir()`, `Path.exists()` and
`Path.is_symlink()` do **not** raise on `OSError`; they catch it and return
`False`."* Independently executed on the review host, over a records dir
behind a mode-000 parent:

```
$ backend/.venv/bin/python   # 3.14.5
Path.exists()      -> False
Path.is_dir()      -> False
Path.is_symlink()  -> False
os.stat            -> raises PermissionError Permission denied

(inspect.getsource(Path.exists) -> returns os.path.exists(self))
```

So the corrected statement is right and the original was wrong in the
reassuring direction, exactly as the correction says. Assessed against the
things a correction of this kind can get wrong:

* **Direction of the error** — correctly characterised as reassuring, not
  merely imprecise.
* **Cause** — correctly characterised as *"one of method, not of honesty …
  reasoned about rather than executed"*. That is the accurate diagnosis and
  it is stated without hedging.
* **Scope** — correctly identifies that item 1's self-description as "the
  honest boundary of what was proven" drew the boundary in the wrong place,
  and the separate ANSWERED block at `:389-399` correctly records that
  governance judged the round-3 remediation *not* to have eliminated the root
  cause. Neither block softens or relitigates round 4's verdict.
* **History preservation** — the original wrong text is retained verbatim
  above the correction, per the project's append-not-rewrite convention. No
  silent rewrite; `git diff` on the file shows additions only.
* **Residual overclaim** — the only forward-looking sentence is *"The defect
  is fixed as of the round-4 remediation; this correction stands regardless,
  because the record itself was wrong."* Scoped to R4-1's named shape, that
  sentence is **true** and I verified it (§5.1). It does not claim the
  invariant family is eliminated, does not claim convergence, and does not
  claim review or promotion. I found no residual overclaim.

One caveat worth recording rather than scoring: the correction is
self-authored by the same implementation lineage whose round-3 text was
wrong, and it asserts *"This session independently re-reproduced that same
output before fixing it"* — a claim whose sole citation does not exist
(R5-2). I re-established the pre-fix behavior's *existence* only indirectly:
MUT-R5-A/MUT-A-class reversions do reproduce a fail-open at this seam, and
round 4's I1/I2 recorded it directly. So the claim is credible and the
correction stands; the trail to it does not.

## 9. Is the 20/20 mutation claim dispositive?

**Partly. It is dispositive for the narrow claim it can support, and it is
NOT dispositive for the central invariant I-1 — and I can prove the latter
rather than argue it.**

What 20/20 genuinely establishes. The seven round-4 additions are not
incidental-line mutants: M14 restores the pathlib `is_dir`/`exists` gate (the
literal R4-1 root cause); M15 folds a metadata `OSError` back into `absent`;
M16 restores `main()`'s second filesystem probe; M17 silences
`UNCLASSIFIABLE_RECORDS_ENTRY`; M18 re-permits a notice beside a `BLOCKED`
verdict; M19 folds the broken-symlink case into `absent`; M20 re-probes entry
type through pathlib in the consumer. Those are precisely the tri-state and
error-propagation branches at issue, each reverted by a different route, and
each is killed. I verified the harness is not self-deceiving: it refuses the
whole run (exit 2) if any anchor does not match exactly once, it asserts a
sane unmutated baseline before claiming any kill, and it re-asserts the real
files' SHA-256 in `finally`, at interpreter exit, and on SIGINT/SIGTERM. My
own MUT-R5-A and MUT-R5-B add two reversions the authored set does not
contain (a class-evading `os.path.*` reintroduction, and the stat-vs-lstat
choice) and both die to behavioral tests. **Conclusion: the tri-state guards
that exist are load-bearing, independently detected, and not reversible in
one line.** That is a real and materially stronger result than rounds 1-3.

Why it is not dispositive for I-1. The set is, by construction, enumerated
from the fixes that were written — the remediation record's own §7 item 8
says as much (*"it says nothing about defects outside the set"*), and round 4
demonstrated the consequence when an 11/11 and then a 13/13 battery were
green while a live fail-open existed. The decisive test of dispositiveness is
whether the all-killed score coexists with a live violation of I-1 **right
now**, and it does: **R5-1 is live at HEAD while 55/55 tests pass and 20/20
mutants die.** Concretely, `acquire_records_dir`'s inner
`except OSError: return RecordsPath(RECORDS_PATH_ABSENT, None)`
(`:452-453`) is carrying an unknown-into-absent fold that

* no mutant in the battery anchors on (M15 mutates the *outer* handler, M19
  mutates the sibling `BROKEN_RECORDS_SYMLINK` return),
* no test exercises (the one helper built to exercise it,
  `_with_injected_stat(..., also_lstat=False)`, is never invoked that way),
  and
* the module's own docstring asserts cannot exist.

So 20/20 is dispositive evidence of *guard quality* and emphatically **not**
evidence of *invariant coverage*. The structural locks
(`test_no_pathlib_existence_probe_decides_a_pass_or_notice`,
`test_main_does_not_rediscover_records_after_validation`) were the round-4
attempt to escape exactly this limitation, and they are a genuine
improvement — but R5-7 shows the AST lock's ban list is narrower than the
class it claims to close, and neither lock looks at `acquire_records_dir`'s
internal error classification at all. A battery plus two locks still does not
substitute for an enumeration of the error-classification branches
themselves; a decision-level check that every `except` clause in
`acquire_records_dir` is reached by a test would have found R5-1.

## 10. Continuity — disposition of prior-round open findings

| Finding | Prior state | My disposition | Evidence |
|---|---|---|---|
| **R4-1** P2 (unreadable ancestor → exit 0, PASS, false absent-notice; default invocation) | OPEN, recurrence 3 | **CLOSED** on its named shape, both flag modes, at parent and grandparent depth, with a discriminating readable control | §5.1 |
| **R4-2** P2 (round-3 record's false fail-closed claim) | OPEN | **CLOSED as to content** — correction is accurate, no residual overclaim; **re-opened as R5-2 as to evidence trail** (citation dangles, no round-4 implementation record) | §8, §7 R5-2 |
| R4-3 P3 (unnamed tracebacks: unreadable/non-UTF-8/mid-traversal record) | OPEN, carried | **CARRIED unchanged**, re-executed; one new member (unix socket), and one qualitatively worse new member split out as R5-3 (FIFO → hang) | §5.5, R5-3/R5-4 |
| R4-4 P3 (bare `return` instead of skip in live drills) | OPEN | **PARTLY CLOSED** — the five new round-4 drills use a reported `_skip()`; the two round-3 drills still bare-`return` (in-line acknowledged). Carried as R5-5 | §7 R5-5 |
| R4-5 P3 (test docstring names a mechanism it does not use) | OPEN | **CARRIED verbatim** as R5-6 | §7 R5-6 |
| R4-6 P3 (`SCENARIOS.md` stale execution-evidence pointer) | OPEN | **NOT RE-TESTED — out of this review's scope** (scenario/requirement status rows were excluded by charter). Remains open on the round-4 record | §2 |
| R3-2 P3 (unknown front-matter keys silently ignored) | carried | **CARRIED unchanged, no ordering bypass** — decoy `Phase: expand` beside authoritative `phase: contract` still enforces `contract`: exit 1, `OUT_OF_ORDER_PHASE … starts at 'contract'` | executed |
| R3-3 P3 (absolute host paths in messages) | carried | **CARRIED unchanged** — root-level problems print the absolute path (§5.1), nested print relative (§5.4). No widening; the absolute path is already on the unconditional "Records dir checked:" line | executed |
| R3-4 P3 (no CI wiring; `--require-dir` omitted) | carried | **CARRIED unchanged** — `knowledge/05-QA/tools/run_regression.py:61-64` still registers the lint with no `--require-dir`; `.github/workflows` still absent. This is what keeps the default-mode path the operative one, and therefore what makes R5-1's blast radius the default invocation | executed |
| R2-1 / R2-2 / R2-3 (closed at round 3) | closed | **Guards re-confirmed firing**, not relitigated: e6 `SYMLINK_IN_RECORDS_TREE`, duplicate-key and not-a-directory paths killed by M10/M11 | §5.3, §4 |

## 11. Verdict

**BLOCKED_P0_0_P1_0_P2_2_P3_6**

The round-4 cross-layer strategy worked on its own terms: the tri-state
acquisition is the right architecture, R4-1's shape is genuinely closed in
both flag modes, the notice can no longer contradict the verdict, the tool is
demonstrably read-only, and for the first time a class-evading reintroduction
of the root cause is killed by behavioral tests rather than by a
shape-specific guard. That is material progress, and the round-3 accuracy
correction is honest and correct.

It is nonetheless BLOCKED on two P2s. R5-1 is the same unknown-folded-into-
absent fold, surviving at the one error-classification branch that no test
and no mutant touches, and contradicted by the module's own docstring — I
down-rated it from the charge's P0/P1 default to P2 strictly on reachability
(race-only), and said so explicitly so governance can escalate if it
disagrees. R5-2 is that the change under review has no implementation record
at all and the round-3 correction's only citation points at a file that was
never written, so nothing durable pins the reviewed bytes or carries the
limitation set forward.

SCN-MOD001-070 remains **EXECUTED — NOT PROMOTED**. I set no scenario status,
changed no convergence state, certified nothing, and issued no Module
Approval Certificate.

## 12. Limits — what I did NOT do

- Did not run the backend suite, Docker/Postgres probes, or any unrelated
  gate; execution was bounded to the four scoped files plus `mypy`/`ruff` on
  the two scoped sources.
- Did not open, read for verdict, resume, or dispatch **any** DOM-002
  artifact.
- Did not review or re-test scenario status, requirement rows, module
  certification, or any other MOD-001 slice — including R4-6, which therefore
  stays open unadjudicated.
- Did not search exhaustively for a *static* filesystem shape that reaches
  R5-1; I tried the shapes in §5.1/§5.3 and found none, so "race-only" is a
  reasoned conclusion from a bounded search, not an exhaustive proof.
- Could not create a block/char device fixture without privileges, so the
  wrong-type matrix covers regular file, FIFO, unix socket and `/dev/null`
  only.
- Did not verify `mr_verify.py`'s own correctness and did not run it; model
  attestation is performed externally by the orchestrator.
- Live-permission results depend on this host (uid 501, macOS/APFS)
  enforcing mode 000; it does. Behavior may differ as root or on a
  permission-ignoring mount — which is what the injected tests exist to
  cover.
- Throwaway fixtures lived under `/tmp/scn070r5*` only; modes were restored
  and the trees removed at closeout. Repo hashes re-verified unchanged after
  every drill (§1 values).

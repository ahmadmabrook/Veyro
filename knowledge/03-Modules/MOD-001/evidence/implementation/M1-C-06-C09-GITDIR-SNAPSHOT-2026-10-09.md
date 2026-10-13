---
doc: M1-C-06 C09-X git-vs-CI checkout contradiction — git-free committed-snapshot boundary
status: CANDIDATE_ONLY — NOT APPROVED FOR REAL-TREE OR CI SCANNING
date: 2026-10-09
runner_operation: 3e4973e2-7959-4320-9f33-d82e3a31c106
bounded_operation: M1-C-06 (final audited dispatch, v30)
subgoal: M1-C-06-C09-GITDIR-SNAPSHOT-BOUNDARY
---

# The contradiction this dispatch resolves

`.github/workflows/c06-real-tree-scanner-candidate.yml` fetches a Git checkout
into `$RUNNER_TEMP/head` — it has to, because Git is what proves the tree is the
exact pushed commit, and the wrapper's target enumeration reads the Git index.
`tools/governed_scanner_preflight.py` `run_gitleaks_governed` refuses any target
containing `.git`, because `gitleaks dir` walks a *directory* and would put Git
object/pack bytes (history — a surface CAP-009 records as NOT approved) in front
of the scanner. `invoke` passed `repo_root` straight to that function as the
gitleaks target, so the authorised gitleaks branch was structurally unreachable:
a clean committed checkout necessarily contains `.git`, so a future authorised
run could only ever have exited 2. That was v29's recorded blocker
(`C09_X_DORMANT_INVOKER_PARTIAL_WITH_BLOCKER`).

The two requirements are not in conflict once they are assigned to two different
directories, which is the whole of the change: the checkout is the *source of
reviewed bytes* and is never a scan target; the scan target is a materialization
of exactly the enumerated committed blobs that contains no Git object at all.

# What changed

`tools/governed_scanner_preflight.py`:

* `materialize_tracked_snapshot(live, repo_root, work)` copies exactly the
  enumerated tracked paths into `<work>/committed-snapshot` (always outside the
  repository) and returns that path plus a content digest over
  `path\0sha256(bytes)` lines. Every file's bytes are hashed into their Git blob
  id (`_blob_oid`) and compared against that path's Git index entry, so
  working-tree bytes that are not the committed blob (filter, EOL conversion,
  editor race) refuse rather than being scanned as if reviewed. It refuses on
  index drift between enumeration and copy, a pre-existing destination, a
  destination inside the source repository, any symlink violation, any unsafe
  path component (`.git`, `..`, empty), a non-regular enumerated file, a
  post-copy file set that is not exactly the enumerated set, and any symlink or
  `.git` present in the result.
* `_VEYRO_DERIVED_TARGETS` / `_is_veyro_derived` plus one added clause in
  `_require_scan_allowed`: the snapshot destination is registered **before the
  first byte is written**, and the choke point treats it — and anything under it
  — exactly as it treats a path inside the repository. This is the control that
  keeps copying bytes out of the repo from silently reclassifying a Veyro scan
  as approved synthetic scope. It is append-only within a process and consulted
  in one direction only: it can add a refusal, never remove one. There is no
  caller-supplied parameter, flag, env var or marker involved.
* `veyro_relative_findings` maps a finding's `File` back to the reviewed
  repository-relative path, and refuses any `File` it cannot place inside the
  snapshot — a path that cannot be mapped to an enumerated target is not
  evidence about the reviewed bytes, and a bare temp path would be unverifiable
  once the run ends.
* `invoke`'s gitleaks branch materializes after every target-side refusal and
  after artifact identity, scans the snapshot, maps the findings, and removes
  the snapshot in a `finally` — no copy of the tree outlives the run. The report
  records `materialized_snapshot` (`file_count`, `content_sha256`, `git_free`,
  `retained_after_run`). **CORRECTED — this bullet as written was false for a
  failure inside materialization itself, and the `retained_after_run` value it
  describes was unconditional. See "Independent post-dispatch correction" and
  "Mandatory cleanup correction applied (v31)" below; read those two sections
  as governing this bullet.**
* `_staged_entries` factors the `git ls-files -s -z` parse (now carrying the
  blob id) out of `enumerate_targets`; the `.git`-in-target refusal is kept
  verbatim as a backstop for any caller that skips materialization.

`.github/workflows/c06-real-tree-scanner-candidate.yml`: comment-only addition
stating why the job fetches a checkout and that the scan target is the git-free
materialization. Verified comment-only (lines 35–44 all `#`), top-level keys and
`run:` bash blocks unchanged (`bash -n` clean).

`tools/governed_scanner_targets.json` and `CAPABILITY_REGISTRY.md` were **not
touched**: manifest SHA-256 is unchanged at
`a62f618ed4080e6e12203e7408979f76e2ac141d33ea117949b0b5ad6283509d`. No grant,
determination pointer, advisory pointer, registry row or scenario disposition
was edited.

# Verification performed

No scanner was executed against any Veyro file, index, history or copy, in any
step below. gitleaks was not executed at all; Ruff executed only against pytest
`tmp_path` fixtures outside the repository (CAP-010's approved bounded scope) and
as a linter.

`backend/.venv/bin/python -m pytest tools/tests/test_governed_scanner_preflight.py -q`
→ **80 passed** (was 69; +12 new, −1 replaced). The replaced test was the one
asserting the contradiction itself
(`test_authorised_gitleaks_path_refuses_a_checkout_containing_dot_git`); its
backstop is now covered by `test_a_target_directory_containing_dot_git_is_still_refused`
against a synthetic checkout-shaped directory. `py_compile` clean on both files.
`ruff check` reports one pre-existing `ISC004` in `gate_mode_refusals`, code this
dispatch did not touch; it is not introduced here and was not fixed (out of
scope). The file was already not `ruff format`-conformant before this change.

Disposable synthetic Git checkout, created outside the repository, materialized
and inspected (demonstration script run then deleted; the same properties are
asserted permanently by the tests):

| Property | Observed |
|---|---|
| source checkout contains `.git` | True |
| enumerated tracked targets | 3 — `backend/app.py`, `node_modules/b.py`, `pkg.py` |
| snapshot file set == enumerated set | True (3 files) |
| any `.git` anywhere in snapshot | False |
| snapshot bytes == checkout bytes, per path | True |
| snapshot blob-oid == Git index entry, per path | True |
| snapshot `content_sha256` | `32459a53668194747df7bc5e4988d3757bb501687416f8cc93aa4a83c729f8aa` |
| snapshot located outside the Veyro repository | True |
| choke point treats snapshot as Veyro-derived | True |
| scanning that snapshot without a grant | `RealScanBlocked`, 5 blockers, first = missing `GRANT-REAL-TREE-DIR-SCAN: CAP-009` |
| modified working-tree byte, blob unchanged | refused: hashes to blob `407de306…`, not the indexed id |
| path added to the index after enumeration | refused: index changed, 1 path `['intruder.py']` |

The real current checkout remains denied, both scanners, unchanged by this work:
`scan --scanner gitleaks` and `scan --scanner ruff` each exit **3** naming five
blockers (no registry grant token, no authorising determination named, and
wrapper/manifest/workflow all untracked); `preflight` reports
`authorised_for_real_tree_scan=False` with
`clean_committed_checkout=False` (750 modified/untracked entries). Authorisation
is asked before materialization, so a blocked run creates no copy of any Veyro
byte — asserted by `test_blocked_invoke_materializes_no_copy_of_the_tree`.

Artifact hashes after this dispatch:

| Artifact | SHA-256 |
|---|---|
| `tools/governed_scanner_preflight.py` | `ab978188f8ca56e58622853b0dbdd6502b0ce2f8e7775081ceb78520e614b8e4` |
| `tools/tests/test_governed_scanner_preflight.py` | `a992281751e1c16e6264302257f849ba3ff64007d4670ac9973a08a2c1ad0854` |
| `tools/governed_scanner_targets.json` | `a62f618ed4080e6e12203e7408979f76e2ac141d33ea117949b0b5ad6283509d` (unchanged) |
| `.github/workflows/c06-real-tree-scanner-candidate.yml` | `b5ba33e61adf3524e7ec8ac0167853abfd8fc78db6c2deda90c3c084e1b3c2d8` |

Baselines re-verified at session start: 4/4 PASS against `PROJECT_INDEX.md`.

# Fail-closed properties preserved (re-checked, not assumed)

Order in `invoke` is manifest drift → vacuity/symlink → clean committed checkout
→ advisory-before-gate → work-dir-outside-repo → artifact digest → pinned
version → **materialization** → governed argv. So: manifest target-set binding,
clean-committed-checkout, no-unreviewed-bytes, symlink refusal, suppression
refusals (`--ignore-gitleaks-allow`, no `--baseline-path` in any form,
target-root `.gitleaksignore` refused, verified-empty `-i` directory), artifact
pin re-verified every run, advisory-before-gate sequencing, and the exit contract
(0 clean / 1 gate findings / 2 refused / 3 blocked) all still hold, and all of
them now run *before* any byte is copied. The `-i` ignore directory and the JSON
report live as siblings of the snapshot under the work directory, not inside the
scan target, so neither becomes a target.

# Residuals — exact, not optional

1. **No grant exists and none was created.** CAP-009/CAP-010 remain APPROVED
   (BOUNDED) for synthetic `dir`/`S` scope only. This dispatch makes a future
   authorised gitleaks path *reachable in principle*; it authorises nothing. The
   registry row, the authorising-determination pointer and the advisory-run
   pointer are all still absent, and this wrapper cannot create any of them.
2. **The authorised gitleaks path has still never executed real gitleaks.** It
   is proven only through a digest-pinned fake executable inside a disposable
   repository. C09-X item 4 (evidence for the mode the gate uses) is not closed.
3. **The linux extracted-binary digest is still unpinned**, so an authorised CI
   run would refuse at exit 2 on `verify_artifact_digest`. That pin is a
   determination's to record. Unchanged by this dispatch.
4. **The three bound files remain untracked**, so `iac.md` control 1 is unmet by
   construction and the blocker list cannot empty on this machine. Independent
   code/security review of this exact snapshot is still required before any
   grant.
5. **Snapshot-level residuals.** A tracked `.gitleaksignore` at repository root
   would be copied into the snapshot root and then refused by
   `run_gitleaks_governed` (fail-closed, and Veyro tracks none today); whether
   8.30.1 honours a non-root `.gitleaksignore` is UNTESTED. `_blob_oid` assumes
   sha1 object format — a sha256-format repository refuses rather than being
   silently accepted. The `_VEYRO_DERIVED_TARGETS` registry is per-process: it
   governs snapshots this module creates, not an arbitrary copy some other tool
   might make.
6. **No capability or scenario verdict is claimed here.** No CAP row changed, no
   R03/R04 gate relies on either scanner, no scenario moved, the candidate
   workflow is still untracked/unrun/non-required/inert, and nothing was pushed
   or promoted.

# Independent post-dispatch correction — mandatory cleanup blocker

The structural `.git`-versus-`dir` contradiction is resolved on the synthetic
authorized path, but the claim above that no copy outlives **every** run is too
broad. Independent deterministic reproduction in a disposable synthetic Git
repository committed `a.txt` and `z.txt`, then changed only `z.txt`. The call
`materialize_tracked_snapshot(live, repo, work)` correctly refused the later
blob mismatch, **but left `<work>/committed-snapshot/a.txt` on disk**. The
focused suite still passed 80/80 because it asserted the refusal, not cleanup.
No scanner or Veyro byte was used in this reproduction.

Cause: `invoke` enters its `shutil.rmtree(snapshot)` `finally` only after
`materialize_tracked_snapshot` returns. A refusal during its copy loop occurs
before that `finally` is established. This is a mandatory security/data-handling
defect in the newly authored snapshot path, not a grant or scenario verdict.
The candidate must remove partial materialization on every failure and must not
claim `retained_after_run: false` when cleanup has not been verified. Keep
CAP-009/010 real-tree and CI scanning blocked. The exhausted 47-dispatch C06
audit requires a fresh scope decision before any further guarded call.

# Mandatory cleanup correction applied (v31)

Operation `f1925b9b-068c-4544-bc38-2fc9e2f13cc9`, subgoal
`M1-C-06-C09-SNAPSHOT-FAILURE-CLEANUP`. Scope was the reproduced partial-
snapshot defect only: `tools/governed_scanner_preflight.py` and
`tools/tests/test_governed_scanner_preflight.py` were the only files changed.
No registry, grant, manifest, workflow, control or dashboard file was touched,
nothing was pushed, no review or scenario promotion occurred, and no second
strategy was attempted.

## What changed

* `_discard_snapshot(dest)` (new) removes a snapshot and then **re-checks that
  it is gone**, returning a description of whatever survived rather than None.
  `shutil.rmtree(ignore_errors=True)` reports nothing, so it cannot by itself
  support a claim that cleanup happened.
* `materialize_tracked_snapshot` now wraps every step that can write a byte —
  index-drift check, the copy loop, the post-copy file-set and git-free/symlink
  checks — in a guard that discards the destination before propagating **any**
  exception (`BaseException`, so an interrupt mid-copy is covered too, since it
  leaves exactly the same partial copy a refusal does). Cleanup is this
  function's own obligation because a caller's `finally` is only established
  once it returns, which is precisely the cause recorded above. If the residue
  cannot be removed, the original cause and the retained path are raised
  together as a `GovernedScanRefused`. The pre-existing-destination refusal
  still runs *before* the guard, so a caller's earlier snapshot is never
  deleted by a later call's failure.
* `invoke` no longer writes `retained_after_run: false` at materialization
  time. The field is set only inside the `finally`, from the result of an actual
  `_discard_snapshot` check, with `retention_residue` added when something
  survived; a surviving copy raises `GovernedScanRefused` even after an
  otherwise clean or findings-only scan, because reviewed bytes outliving the
  run is itself the defect.

## Observed results

`backend/.venv/bin/python -m pytest tools/tests/test_governed_scanner_preflight.py -q`
→ **85 passed** (was 80; +5, none replaced, none weakened). `py_compile` clean
on both changed files.

Non-vacuity of the new tests, measured rather than asserted: the two added
cleanup behaviours were neutered in place (`residue = None` in the
materialization guard; the old unconditional `retained_after_run: False` in
`invoke`) and the new tests re-run — **4 of the 5 failed**, including
`test_a_later_path_blob_mismatch_leaves_no_partial_snapshot`, the exact
reproduction. The fifth, `test_a_scanner_error_discards_the_snapshot_and_records_it`,
passed pre-fix: that exit was already covered by the caller's `finally`, so it
is stated here as a regression lock on an exit that previously worked, not as
evidence of a second bug fixed. The module was then restored from a byte-exact
backup (SHA-256 re-verified identical) and the full focused suite re-run at
85/85.

| New test | Covers | Pre-fix |
|---|---|---|
| `test_a_later_path_blob_mismatch_leaves_no_partial_snapshot` | sorted enumeration `a.txt`/`z.txt`, mismatch on the second: refusal must leave no `a.txt` and nothing under the work dir | FAILED |
| `test_an_unexpected_error_during_the_copy_also_leaves_no_partial_snapshot` | `OSError` on the second write (not a refusal) | FAILED |
| `test_a_refusal_whose_cleanup_fails_names_the_retained_copy` | removal primitive neutered: refusal must name the retained path and keep the original cause | FAILED |
| `test_an_unremovable_snapshot_turns_a_clean_scan_into_a_refusal` | clean scan + unremovable copy → exit 2, `retained_after_run: true`, `retention_residue` | FAILED |
| `test_a_scanner_error_discards_the_snapshot_and_records_it` | scanner rc=7 → refusal, snapshot gone, `retained_after_run: false` | passed (caller `finally` already covered this exit) |

The existing report-mapping refusal test now also asserts
`retained_after_run is False`, so the honest field is checked on that exit too.

Live denial re-confirmed, no `--binary` supplied, no Veyro file, index, history
or copy scanned, and no scanner process started at all:

| Live command | Exit | Blockers | `materialized_snapshot` |
|---|---|---|---|
| `scan --scanner gitleaks` | **3** | 5 (no CAP-009 grant token, no authorising determination, wrapper/manifest/workflow untracked) | absent |
| `scan --scanner ruff` | **3** | 5 (same, CAP-010 token) | absent |

Artifact hashes after this correction:

| Artifact | SHA-256 |
|---|---|
| `tools/governed_scanner_preflight.py` | `2bc17b2ea365f8813ab568228bc163b0bacc1f217b283d20e84c4e36d736ba70` |
| `tools/tests/test_governed_scanner_preflight.py` | `c35b97089ccf1b1840bf419446186797419b1ae51e159ee4df0dc73dc241d6a6` |
| `tools/governed_scanner_targets.json` | `a62f618ed4080e6e12203e7408979f76e2ac141d33ea117949b0b5ad6283509d` (unchanged) |
| `.github/workflows/c06-real-tree-scanner-candidate.yml` | `b5ba33e61adf3524e7ec8ac0167853abfd8fc78db6c2deda90c3c084e1b3c2d8` (unchanged) |

Baselines verified at session start: 4/4 PASS against `PROJECT_INDEX.md`.

## Residuals specific to this correction

1. **The cleanup-failure path is proven with the removal primitive stubbed**,
   not against a genuinely undeletable directory. What is demonstrated is that
   `_discard_snapshot`'s independent existence check — not `rmtree`'s silence —
   is what decides the reported value; the behaviour against a real permission-
   denied or locked residue is UNTESTED.
2. **No forced removal is attempted.** An undeletable residue is reported and
   refused, never chmod'd or escalated around. That is deliberate but means a
   retained copy can still exist on disk after a refusal; the report then says
   so, which is the honesty property, not an absence property.
3. **An interrupt mid-copy whose cleanup fails surfaces as
   `GovernedScanRefused`** rather than propagating the interrupt. Chosen so the
   retained path is never silent; it does mean `KeyboardInterrupt` can be
   reported as a refusal in that one case.
4. **Everything in "Residuals — exact, not optional" above still stands
   unchanged.** No grant exists, real gitleaks has still never run on the
   authorised path, the linux binary digest is still unpinned, the three bound
   files are still untracked, and CAP-009/CAP-010 real-tree and CI scanning
   remain blocked. This correction closes a defect in the candidate; it moves
   no capability, scenario or gate, and the candidate still requires independent
   code/security review before any grant.

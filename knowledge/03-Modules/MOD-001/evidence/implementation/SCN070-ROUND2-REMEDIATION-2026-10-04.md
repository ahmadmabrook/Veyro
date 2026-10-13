---
doc: SCN070-ROUND2-REMEDIATION
module: MOD-001
requirement: GOV-01-R06 (Database-change policy/tooling), TSD §24.2
scenario: SCN-MOD001-070 (MIG · Blocker · negative)
round: 2 remediation
date: 2026-10-04
status: REMEDIATED — NOT REVIEWED, NOT PROMOTED
---

# SCN-MOD001-070 — Round-2 Remediation (R2-1, R2-2, R2-3)

Implementation-tier record. **Not** a self-approval, **not** an independent
review, **not** a promotion of SCN-MOD001-070, **not** a module
certification. No reviewer was launched from this session.

Report remediated:
`../security/SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND2-2026-10-04.md`
(BLOCKED, P0=0 / P1=0 / P2=3 / P3=4).

Bounded scope: the three P2 findings only. R2-4 … R2-7 (P3) were not the
charge; what moved on them anyway is stated in §6, and what did not is
stated in §7.

---

## 1. Runtime model/session evidence

Same session as the round-1 remediation (`fc84a793-79c0-4a6f-b491-b061ea27746f`),
resumed — not a new session, so the round-1 runtime proof extends rather
than being replaced. Re-verified against the live transcript at this
round's closeout:

```
$ backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py \
    ~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/fc84a793-79c0-4a6f-b491-b061ea27746f.jsonl \
    opus scn070-remediation-implementation-session
{
  "verdict": "PASS",
  "reason": "144 turn(s), 100% consistent, model 'claude-opus-5' matches required tier 'opus'.",
  "models_observed": ["claude-opus-5"],
  "expected_tier": "opus"
}
EXIT=0
```

144/144 assistant turns resolve to `claude-opus-5`, an exact member of
`mr_verify.py`'s DC-17-qualified Opus allowlist — no mid-task substitution
across both remediation rounds. The routing deviation recorded in the
round-1 record §1 still applies verbatim and unchanged: GOV-01-R06's lint is
not one of `veyro-critical-engineer`'s three ADR-005-bounded slices, so that
role was **not** invoked; the Opus tier was honored and runtime-verified
instead. Full MR record:
`../model-routing/SCN070_R1_REMEDIATION_RUNTIME_PROOF_2026-10-04.md`.

---

## 2. Fixes

All three are **structural fail-closed guards**, not message changes. Round
2 was explicit that narrowing a docstring claim would not be adequate
because the clean exit-0 PASS would survive; none of these three fixes
relies on wording.

### R2-1 — symlinks in the records tree (`tools/validate_migration_ordering.py`, `discover_records`)

```python
if path.is_symlink():
    problems.append(f"{relative}: SYMLINK_IN_RECORDS_TREE — ...")
    continue
```

Placed **before** the `is_dir()` branch, which was the whole defect:
`is_dir()` follows the link and returned `True`, so the symlink `continue`d
out, while `rglob` independently refused to descend through it. Both the
recursion path and the reporting path missed it.

Reported rather than followed, deliberately. Following link targets would
widen the walk and invite cycles and escapes outside the records tree;
reporting fails closed in three lines without resolving anything. This is
the shape round 2 called for.

### R2-2 — duplicate front-matter keys (`parse_front_matter`)

```python
if key in fields:
    raise RecordError(f"{path.name}: DUPLICATE_FRONT_MATTER_KEY — '{key}' declared more than once ...")
```

Refusing, not resolving. Picking either occurrence is a guess about author
intent; `RecordError` was already the right vehicle and is already caught by
`validate_directory`, so this is one branch and no new plumbing. Applies to
**every** key, not just `phase` — a duplicated `change_id` would silently
re-key an ordering chain the same way.

### R2-3 — non-directory records path (`validate_directory`)

```python
if not records_dir.is_dir():
    if records_dir.exists():
        return [f"{records_dir}: RECORDS_PATH_NOT_A_DIRECTORY — ..."]
    if require_dir:
        return [f"{records_dir}: MISSING_RECORDS_DIR — ..."]
    return []
```

`exists()` → `is_dir()`, with the two causes split so the diagnostic still
names the real problem.

**One judgment call beyond the literal suggestion, stated explicitly:**
round 2 proposed changing the condition; this makes
`RECORDS_PATH_NOT_A_DIRECTORY` fail closed **regardless of `--require-dir`**.
Rationale — the absent-directory pass exists for a real, documented reason
(GOV-01-R06's own OUT-of-scope line: no product schema exists yet), and
`--require-dir` is the opt-in that overrides it. A records path that is a
*regular file* has no legitimate state to protect: it is always a
misconfiguration. Gating that behind an opt-in flag would leave the default
invocation — the one `run_regression.py` actually uses — still passing green
on a botched path. `is_dir()` follows symlinks, so a symlink to a real
records directory keeps working (verified, §4 control G).

---

## 3. Tests — 18 → 29, decisive negatives plus positive controls

`tools/tests/test_validate_migration_ordering.py`. The 18 prior tests are
unchanged. 11 added, each named by finding:

**R2-1 (4).** `test_symlinked_subdir_hiding_destructive_contract_fails_closed`
is the decisive mixed fixture round 2 specified — a **valid complete
4-phase set** for `change_a` *plus* a symlinked `q4/` whose target holds a
lone destructive `contract` for `change_b`. Real records are present, so
neither vacuous-pass notice fires: this was the fully clean,
indistinguishable false PASS. Then its CLI form with `--require-dir`
asserting exit 1 **and** absence of `NOTICE`; a dangling `*.yaml` symlink;
and `test_real_subdir_and_symlink_free_tree_still_behave` as the positive
control that an all-real-records tree still passes and a *real*
subdirectory still yields `UNRECOGNIZED_RECORD_FILE`.

**R2-2 (4).** The exact round-2 Control I record (`contract` first,
`expand` duplicate after the other fields, destructive by its own
`lock_impact`); the transposed order, since round 2 proved the old outcome
turned purely on which duplicate landed last; a duplicated `change_id`; and
`test_single_keys_and_repeated_colons_in_values_still_pass` as the positive
control — a normal record passes, **and** a value legitimately containing a
colon (`lock_impact: ACCESS EXCLUSIVE: ~200ms, low-traffic window only`,
straight out of `TEMPLATE.md`) is still one key, because the parser splits
on the first colon only.

**R2-3 (3).** A regular file as `--records-dir` without the flag and with
it (asserting the two results are identical, i.e. the flag is no longer the
thing that decides); the CLI form asserting exit 1 and that the old
`NOTICE`/"vacuous pass" text is gone; and
`test_symlink_to_a_real_records_dir_is_still_usable` as the positive
control — a symlink passed *as* the records dir is read through and its
ordering violation found, rather than rejected as a non-directory.

```
$ backend/.venv/bin/python tools/tests/test_validate_migration_ordering.py
PASS — all 29 tests passed (discovered dynamically, not hand-listed).
EXIT=0
```

---

## 4. Executed controls — the exact round-2 shapes, re-run

Fixture `/tmp/scn070_r2fix/` (throwaway, outside the repo, deleted at
closeout — §8). `P` = `backend/.venv/bin/python`. Every record synthetic.

The `mixed/` fixture, as seen through the symlink, is the round-2 shape
byte for byte:

```
$ find /tmp/scn070_r2fix/mixed -follow -type f | sort
/tmp/scn070_r2fix/mixed/0001_a_expand.yaml
/tmp/scn070_r2fix/mixed/0002_a_migrate.yaml
/tmp/scn070_r2fix/mixed/0003_a_switch.yaml
/tmp/scn070_r2fix/mixed/0004_a_contract.yaml
/tmp/scn070_r2fix/mixed/q4/0005_b_contract.yaml      <-- destructive, out of order
```

| # | Command (`$P tools/validate_migration_ordering.py …`) | Round 2 observed | Now |
|---|---|---|---|
| A | `--records-dir /tmp/scn070_r2fix/mixed --require-dir` | **exit 0**, clean PASS, no NOTICE (R2-1) | exit **1**, `q4: SYMLINK_IN_RECORDS_TREE — symlinks are not followed, so anything beneath or behind this link would go unchecked; …` |
| B | `--records-dir /tmp/scn070_r2fix/realnested --require-dir` | exit 1 (negative control, already correct) | exit **1**, `q4/0005_b_contract.yaml: UNRECOGNIZED_RECORD_FILE — …` — **unchanged**, confirming the new guard did not absorb the real-subdirectory path |
| C | `--records-dir /tmp/scn070_r2fix/dupkey --require-dir` | **exit 0**, clean PASS (R2-2) | exit **1**, `0001_widget.yaml: DUPLICATE_FRONT_MATTER_KEY — 'phase' declared more than once ('contract' then 'expand'); the record must declare each field exactly once so the phase a reader sees is the phase enforced` |
| D | `--records-dir /tmp/scn070_r2fix/plainfile.txt --require-dir` | **exit 0** + vacuous-pass NOTICE; flag inert (R2-3) | exit **1**, `RECORDS_PATH_NOT_A_DIRECTORY — this path exists but is not a directory, so no record could ever be discovered under it; …`, **no NOTICE** |
| E | `--records-dir /tmp/scn070_r2fix/plainfile.txt` (no flag) | exit 0, identical to D | exit **1**, identical to D — the flag is no longer what decides |
| F | `--records-dir /tmp/scn070_r2fix/ok --require-dir` — **positive control**, legitimate 4-phase set | n/a | exit **0**, PASS, no NOTICE |
| G | `--records-dir /tmp/scn070_r2fix/records_link --require-dir` — **positive control**, symlink *to* a real records dir | n/a | exit **0**, PASS — read through the link, not rejected |
| H | `tools/validate_migration_ordering.py` (real tree, no args) | — | exit **0**, PASS + `NOTICE: records dir exists but contains no migration records — vacuous pass, no record was checked.` — unchanged, the live tree still passes |

No run anywhere prints a vacuous-pass `NOTICE` alongside a `BLOCKED`
verdict.

---

## 5. Mutation evidence — prior 8 preserved, 3 added, 11/11 killed

```
$ backend/.venv/bin/python knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py
m0 baseline (unmutated): SANE — unit exit 0, PASS — all 29 tests passed (discovered dynamically, not hand-listed).
M1 check_ordering returns [] immediately: KILLED by unit+cli-negative+cli-lone
M2 ordering predicate accepts any skip-ahead: KILLED by unit+cli-negative
M3 start-phase guard neutralized (R1-1, SURVIVED at round 1): KILLED by unit+cli-lone
M4 validate_fields returns [] immediately: KILLED by unit
M5 main() rejection exit code neutralized (R1-2, SURVIVED at round 1): KILLED by unit+cli-negative+cli-lone
M6 discovery narrowed back to glob('*.yaml') (R1-3 fix removed): KILLED by unit
M7 UNRECOGNIZED_RECORD_FILE suppressed (R1-3 fix removed): KILLED by unit
M8 --require-dir neutralized (R1-4 fix removed): KILLED by unit
M9 symlink guard neutralized (R2-1 fix removed): KILLED by unit
M10 duplicate front-matter key last-wins again (R2-2 fix removed): KILLED by unit
M11 non-directory records path accepted again (R2-3 fix removed): KILLED by unit

real tool sha256 unchanged:  34b3a43b9d55cec552be096e4d70e76f986c302eff367e2f31f068607c4a81be
real test sha256 unchanged:  79d369d9cff6d14ac6540d76a7ac6407afbc4cac359ffb82df506ca47e6cc8c3
11/11 mutations killed; survivors=[]
round-1 survivors now killed: ['M3 start-phase guard neutralized (R1-1, SURVIVED at round 1)', 'M5 main() rejection exit code neutralized (R1-2, SURVIVED at round 1)']
```

**M1-M8 kill signals are identical to round 1's** — the round-1 8/8 is
preserved, not merely re-asserted. M9-M11 revert each new guard to the
exact pre-fix behavior round 2 reproduced.

**One harness correction worth a reviewer's attention.** M7's anchor was the
`relative = path.relative_to(...)` assignment, which the R2-1 fix moved to
the top of the discovery loop. On first run after the fix, M7 therefore
inserted `continue` as the loop's **first** statement and suppressed *all*
discovery — a strictly broader mutant than intended, and it showed up as
`KILLED by unit+cli-negative+cli-lone` instead of round 1's `unit`. Caught
and re-anchored to the `UNRECOGNIZED_RECORD_FILE` append itself; M7 is back
to `KILLED by unit`, matching round 1 exactly. Recorded rather than quietly
fixed, because a drifted anchor is precisely how a mutation harness starts
reporting kills it did not perform.

---

## 6. R2-4 — partially closed as a side effect, stated precisely

The R2-1 guard runs before `parse_front_matter`, so a **dangling `*.yaml`
symlink** is now a named `SYMLINK_IN_RECORDS_TREE` problem instead of an
uncaught `FileNotFoundError` traceback (covered by
`test_dangling_yaml_symlink_is_a_named_problem_not_a_traceback`). That is
the symlink half of R2-4 only.

**Still open:** the unreadable-permissions and non-UTF-8 cases round 2 also
named. `validate_directory`'s `try` still catches `RecordError` only, so a
permission-denied or undecodable record still dies with a traceback. Not
fixed — out of this pass's bounds, and R2-4 is P3 (it fails closed and
loudly; the defect is diagnostic quality). The one-line widening round 2
suggested (`except (RecordError, OSError, UnicodeDecodeError)`) remains
available.

---

## 7. Not done, and remaining gaps

1. **R2-5 (P3)** — backward-jump diagnostic still misnames a phase
   regression as a missing predecessor ("jumps to 'expand' without a
   preceding 'contract'"). Fails closed, exit 1; text only. Carried forward
   from round-1 R1-7, still unfixed, still accurately disclosed.
2. **R2-4 (P3), residual** — see §6.
3. **R2-7 (P3) / R1-5 — the gate is real but still vacuous.** `records/`
   holds only `.gitkeep`, which is legitimate (no product schema exists).
   `run_regression.py` registers the lint without `--require-dir`, and
   `.github/workflows` still does not exist anywhere in the repo
   (re-verified). Real CI wiring remains an **explicit GOV-01-R04
   obligation**, not an assumed one. Note that R2-3's fix now makes the
   default invocation fail closed on a non-directory path, so the
   unflagged gate is less inert than it was — but a *missing* directory
   still passes without the flag, by design.
4. **R2-6 (P3) record drift — fixed.** The test docstring no longer
   enumerates test numbers at all (it groups by finding), so it cannot
   drift again. The round-1 remediation record's four positional citations
   ("tests 7-8", "tests 11-14", …) were replaced with test *function
   names*, and a dated amendment was appended to it recording that round 2
   found R1-3 and R1-4 only **partially** closed and escalated R1-8 to P2 —
   the overstated "FIXED (closed)" claims are corrected in place rather
   than left standing. Its §4/§5 observed outputs (18 tests, 8 mutants) are
   deliberately left as the dated historical record, with a line saying so.
5. **`IGNORED_NON_RECORD_FILES` limitation, unchanged and restated.** A
   file literally named `.gitkeep` or `.DS_Store` containing record-shaped
   content is still skipped. Deliberate trade against failing the repo's
   own default run on Finder metadata.
6. **Symlinks are reported, not resolved.** A legitimate operational need
   to organize records behind a symlink is now a hard failure. Judged
   correct for a Blocker-tier negative scenario — no such need exists today
   (`records/` is empty) — but it is a real behavior change, not a pure
   bug fix.
7. **Mutation score is not a scenario PASS.** 11/11 proves each listed
   mutation is detected by a durable control. It says nothing about defects
   outside this mutant set.

---

## 8. Integrity / fail-closed compliance

- **No commit, push, stash, reset, checkout, or branch change.**
  `git rev-parse --short HEAD` = `e481b81`, unchanged across both rounds.
- **No deletions or renames** — `git status --porcelain | grep -E "^( D|D |R )"`
  returns nothing. Porcelain count 323 → 324 (this record is the +1; the
  round-2 report and watchdog captures were already present).
- **Files this round touched — exactly five:**
  1. `tools/validate_migration_ordering.py` — SHA-256 `34b3a43b9d55cec552be096e4d70e76f986c302eff367e2f31f068607c4a81be`
  2. `tools/tests/test_validate_migration_ordering.py` — SHA-256 `79d369d9cff6d14ac6540d76a7ac6407afbc4cac359ffb82df506ca47e6cc8c3`
  3. `knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py` — SHA-256 `3ab83550445b447fdd467bf3c6b563326dbad4d64d47d24ba57738f15189e5c8`
  4. `backend/migrations/TEMPLATE.md` — SHA-256 `c6f2f72a2b1b410d84014acf8e4db15dba323f2aefa8113cb2c7ffb539b312cf` (authoring rules for duplicate keys and symlinks)
  5. `knowledge/03-Modules/MOD-001/evidence/implementation/SCN070-ROUND1-REMEDIATION-2026-10-04.md` — citations de-numbered + dated amendment appended
  Plus this new record. **`run_regression.py` was not re-edited this round**
  (round 1's two entries already cover the lint and its suite).
- **Not touched:** `SCENARIOS.md` (SCN-MOD001-070 still reads
  `EXECUTED — PENDING INDEPENDENT REVIEW (2026-10-04)`), `CURRENT_STATE.md`,
  `CURRENT_HANDOFF.md`, `REVIEW_IN_FLIGHT.md`, `REQUIREMENTS.md`, every
  `.claude/` file, all four governing baselines, DOM-002 round 5 (remains
  interrupted/non-resumable, out of scope), BUG-048/049/050/051, SCN-067,
  R04/ADR-010 A2, and every unrelated slice.
- **`CURRENT_STATE.md`/`CURRENT_HANDOFF.md` deliberately left to the
  orchestrating session**, same reasoning as round 1 §9: the parent/watchdog
  session writes both concurrently, and a concurrent edit from here risks
  clobbering its in-flight writes.
- **No reviewer launched, no self-approval, no promotion, no
  certification.** `REVIEW_IN_FLIGHT.md` read, not written — its protocol
  governs dispatching a review, and none was dispatched.
- **Aggregate regression:** `run_regression.py` → **FAIL (5/6, 1 N/A)`.
  The single FAIL is the **pre-existing, unrelated** `evidence_integrity_check.py`
  `CURRENT_HANDOFF.md` staleness, identical to `RUN_20261004T114858Z.txt`
  from before this session began. Both migration-ordering checks PASS. This
  round's record: `RUN_20261004T123955Z.txt`. Clearing the staleness needs a
  **commit**, which this session is forbidden to make.
- **Baselines re-verified:** `verify_baselines.py` → `PASS — all 4 governing
  baseline hashes match PROJECT_INDEX.md exactly.`
- **Owner-reserved absolutes respected:** no spend, no paid service, no real
  member data (all fixtures synthetic), no deploy/Production promotion, no
  material product/pricing/business/architecture/scope change.
- **Throwaway fixtures deleted at closeout:** `/tmp/scn070_r2fix/` removed,
  absence confirmed; the kill-check removes its own `tempfile` mirrors in
  `finally` and asserts the real tool's and test file's SHA-256 unchanged at
  exit, on SIGINT/SIGTERM, and in `finally`.

## 9. Next legal action

A **fresh-context independent round-3 review** of this remediation (Opus,
zero context from this session), re-running §4's controls and §5's mutation
battery and probing for fail-opens introduced by the three new guards — the
symlink guard and the always-on non-directory rejection are the two most
worth adversarial attention, being behavior changes rather than pure
additions. Per `SESSION_BOOTSTRAP.md` §4 the dispatching session must write
an `IN_FLIGHT` claim in `REVIEW_IN_FLIGHT.md` **before** the dispatch call
returns. SCN-MOD001-070 may not be promoted before that verdict.

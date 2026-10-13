---
doc: SCN070-ROUND3-REMEDIATION
module: MOD-001
requirement: GOV-01-R06 (Database-change policy/tooling), TSD §24.2
scenario: SCN-MOD001-070 (MIG · Blocker · negative)
round: 3 remediation (architectural root-cause)
date: 2026-10-04
status: REMEDIATED — NOT REVIEWED, NOT PROMOTED
authorization: knowledge/00-System/SCN070-CONVERGENCE-ASSESSMENT-2026-10-04.md
---

# SCN-MOD001-070 — Round-3 Remediation: R3-1 at the enumerator abstraction

Implementation-tier record. **Not** a scenario PASS, **not** a promotion,
**not** a self-approval, **not** an independent review. No reviewer was
dispatched. Convergence status, the review claim, and all DOM-002 artifacts
were left untouched.

Authorized scope, verbatim from the convergence assessment's budget
decision: *one* bounded architectural root-cause remediation under the
changed strategy — "replace glob-driven discovery with explicit
error-reporting directory traversal, preserve symlink and record rules, make
any unenumerable subtree a named nonzero failure, and add invariant-based
readable/unreadable positive-negative tests plus a mutation that removes the
traversal-error guard." That is exactly what was done and nothing else. A
fourth review is **not** pre-authorized by this record.

Report remediated:
`../security/SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND3-2026-10-04.md`
(BLOCKED, P0=0 / P1=0 / P2=1 / P3=3). The single required P2 is R3-1.

---

## 1. Runtime model/session evidence

Same session as the round-1 and round-2 remediations
(`fc84a793-79c0-4a6f-b491-b061ea27746f`), resumed. Re-verified at this
round's closeout:

```
$ backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py \
    ~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/fc84a793-79c0-4a6f-b491-b061ea27746f.jsonl \
    opus scn070-remediation-implementation-session
{
  "verdict": "PASS",
  "reason": "186 turn(s), 100% consistent, model 'claude-opus-5' matches required tier 'opus'.",
  "models_observed": ["claude-opus-5"],
  "expected_tier": "opus"
}
```

186/186 assistant turns resolve to `claude-opus-5`, an exact member of
`mr_verify.py`'s DC-17-qualified Opus allowlist; no substitution across all
three remediation rounds. The routing deviation recorded in round 1 §1 still
applies unchanged: GOV-01-R06's lint is not one of
`veyro-critical-engineer`'s three ADR-005-bounded slices, so that role was
not invoked; the Opus tier was honored and runtime-verified instead. Full MR
record: `../model-routing/SCN070_R1_REMEDIATION_RUNTIME_PROOF_2026-10-04.md`.

Host: uid 501, macOS/APFS, `backend/.venv/bin/python` 3.14.5.

---

## 2. Root cause, independently re-derived before fixing

The convergence assessment classified R3-1 `ROOT_CAUSE_ARCHITECTURAL`: the
same fail-closed exhaustive-discovery invariant as R1-3, R2-1 and R2-3, and
"ad-hoc guards around a `Path.rglob` enumerator that suppresses traversal
errors cannot prove exhaustive discovery."

Re-derived here by direct execution rather than taken on the report's word:

```
uid: 501
mode 000 ENFORCED -> live drill really runs: Permission denied
rglob on unreadable dir: []
scandir raised: PermissionError Permission denied
```

`rglob` returns `[]` exactly where `os.scandir` raises. An unreadable
directory was therefore **indistinguishable from an empty one** at the
enumerator boundary, so `problems` was empty, `main()` returned 0, and the
vacuous-pass branch printed a NOTICE asserting a false fact about a tree it
had never read. **No guard existed to mutate** — which is why the round-2
11/11 mutation battery could not have caught it, and why another top-level
permission check would have been a shape patch rather than a fix.

---

## 3. The fix — one new abstraction, replacing the enumerator

`tools/validate_migration_ordering.py`: new `enumerate_tree(root) -> (entries, problems)`,
and `discover_records` now consumes it instead of `records_dir.rglob("*")`.

```python
def enumerate_tree(root: Path) -> tuple[list[Path], list[str]]:
    entries, problems, stack = [], [], [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as scan:
                children = list(scan)
        except OSError as exc:
            where = str(root) if current == root else current.relative_to(root).as_posix()
            problems.append(f"{where}: UNREADABLE_RECORDS_PATH — ... ({exc.strerror}) ...")
            continue
        for entry in children:
            path = Path(entry.path)
            entries.append(path)
            try:
                descend = entry.is_dir(follow_symlinks=False)
            except OSError:
                descend = False
            if descend:
                stack.append(path)
    return sorted(entries), sorted(problems)
```

Design points that are decisions, not incidentals:

- **`list(scan)` inside the `try`.** `os.scandir` can raise either at open
  or during iteration; wrapping only the call would reintroduce a narrower
  version of the same swallow.
- **Symlink semantics preserved exactly.** `is_dir(follow_symlinks=False)`
  means a symlink is still *yielded as an entry* but never descended —
  identical to `rglob`'s Python-3.13+ behavior. `discover_records`'s existing
  `SYMLINK_IN_RECORDS_TREE` guard therefore still sees it, and no link target
  widens the walk or admits a cycle. This is asserted directly by
  `test_enumerate_tree_still_yields_symlinks_without_descending`, not assumed.
- **`entry.is_dir()` wrapped too.** An entry that cannot even be classified
  is not silently dropped: it is already in `entries` and simply not
  descended.
- **Both lists sorted.** Problem text is part of the evidence record and of
  test assertions, so enumeration order must be deterministic rather than
  stack-pop order.
- **Message scoping consistent with its siblings.** Root named by full path
  (matching `MISSING_RECORDS_DIR` / `RECORDS_PATH_NOT_A_DIRECTORY`); a nested
  directory named by relative path (matching `UNRECOGNIZED_RECORD_FILE` /
  `SYMLINK_IN_RECORDS_TREE`). Asserted both ways in the tests.
- **No new dependency, no new production seam for testability.** The
  deterministic tests patch `os.scandir` directly; the lint keeps calling it
  normally.

Module docstring updated to state the enumeration contract, since the old
absolute claim ("an unreadable or misplaced file becomes a visible failure")
was precisely the claim round 3 proved false for directories.

**Preserved behavior, verified by execution (§5 table B):** symlink
rejection, recognized-record selection, `IGNORED_NON_RECORD_FILES`,
duplicate-key rejection, ordering/field checks, `--require-dir`,
`RECORDS_PATH_NOT_A_DIRECTORY`, the vacuous-pass notices, and `main()`'s
exit-code contract are all unchanged.

---

## 4. Tests — 29 → 36

`tools/tests/test_validate_migration_ordering.py`. The 29 prior tests are
unchanged. 7 added:

**Deterministic injected-`os.scandir` failure (3).** A fake raising
`PermissionError` for one target path only and delegating everything else to
the real implementation:
- `test_unenumerable_root_is_a_named_problem_injected` — the records dir
  itself.
- `test_unenumerable_subdirectory_is_a_named_problem_injected` — the subtree
  case **a top-level-only permission check would miss**: the records dir
  reads fine and holds a *valid complete 4-phase set*, so no vacuous-pass
  notice would fire; also asserts the nested problem is named by relative
  path and does **not** leak the absolute root.
- `test_readable_and_unenumerable_same_tree_discriminate_injected` — the
  decisive pair the round-3 report specified: same directory, same single
  destructive record, only enumerability changed. Readable → the
  `OUT_OF_ORDER_PHASE` the record genuinely earns; unenumerable →
  `UNREADABLE_RECORDS_PATH`, and the two results asserted unequal.

These pass as **any uid, including root**, which is the point: they remove
the platform/permission dependency from the decisive coverage.

**Live `chmod 000` drill (2).** `test_live_chmod_000_directory_fails_closed`
and `test_cli_unenumerable_root_exits_1_with_no_false_vacuous_notice` (the
subprocess form, which cannot share a monkeypatch). Both **return early
(skip)** if `os.listdir` on the mode-000 directory succeeds — i.e. the host
does not enforce it (root, or a permission-ignoring mount) — rather than
failing and manufacturing a platform false positive. The CLI one asserts the
old output is gone: no `PASS`, no "contains no migration records".

**Enumerator positive controls (2).**
`test_enumerate_tree_still_yields_symlinks_without_descending` and
`test_enumerate_tree_is_exhaustive_and_deterministic_on_a_readable_tree`
(every entry of a nested readable tree present, zero problems, sorted).

```
$ backend/.venv/bin/python tools/tests/test_validate_migration_ordering.py
PASS — all 36 tests passed (discovered dynamically, not hand-listed).
EXIT=0
```

**Skip-vs-ran, stated explicitly:** on this host mode 000 was verified
enforced at uid 501 (§2 output), so the two live-drill tests **genuinely
executed**; they did not silently skip. A future run on a root-privileged
container will skip them and still get full R3-1 coverage from the three
injected tests.

---

## 5. Executed controls

Fixture `/tmp/scn070_r3fix/` (throwaway, outside the repo, deleted at
closeout — §8). All records synthetic. `--require-dir` on every run.

### A — R3-1 itself, live `chmod`

| # | Target | Round 3 observed | Now |
|---|---|---|---|
| A1 | `np/` **readable**, one destructive lone `contract` | exit 1, `OUT_OF_ORDER_PHASE` | exit **1**, `0001_destructive_contract.yaml: OUT_OF_ORDER_PHASE — change_id 'drop_members_table' starts at 'contract' but must start with 'expand'` — unchanged positive control |
| A2 | **same** `np/` at mode `000` | **exit 0**, `PASS` + false NOTICE "contains no migration records" | exit **1**, `/tmp/scn070_r3fix/np: UNREADABLE_RECORDS_PATH — could not enumerate this directory (Permission denied), so any migration record under it would go unchecked; a tree that cannot be read must never report a pass` — **no NOTICE, no PASS** |
| A3 | `mixed/` readable with a **valid 4-phase set** + real child `q4/` at mode `000` | not probed by round 3 | exit **1**, `q4: UNREADABLE_RECORDS_PATH — …` — the nested case a top-level check would miss, named relatively |
| A4 | `ok/` legitimate complete 4-phase set | n/a | exit **0**, PASS, no NOTICE |
| A5 | real tree, no args | — | exit **0**, PASS + `NOTICE: records dir exists but contains no migration records — vacuous pass` — live tree still passes, notice still honest |

### B — prior rounds' behavior preserved across the enumerator swap

| Target | Result |
|---|---|
| duplicate `phase:` key (R2-2) | exit **1**, `DUPLICATE_FRONT_MATTER_KEY — 'phase' declared more than once ('contract' then 'expand')` |
| symlinked child dir hiding a destructive `contract` (R2-1) | exit **1**, `q4: SYMLINK_IN_RECORDS_TREE` |
| real nested subdirectory record (R1-3) | exit **1**, `q4/0001_b_contract.yaml: UNRECOGNIZED_RECORD_FILE` |
| symlink **to** a real records dir, passed as `--records-dir` (R2-3 positive) | exit **1** on the record's own `OUT_OF_ORDER_PHASE` — read through the link, as documented |
| regular file as `--records-dir` (R2-3) | exit **1**, `RECORDS_PATH_NOT_A_DIRECTORY` |

### C — gates

```
$ backend/.venv/bin/python knowledge/00-System/verify_baselines.py
PASS — all 4 governing baseline hashes match .../PROJECT_INDEX.md exactly.   (exit 0)

$ git diff --stat -- tools/validate_migration_ordering.py tools/tests/test_validate_migration_ordering.py backend/migrations/TEMPLATE.md
 backend/migrations/TEMPLATE.md                  |  28 +
 tools/tests/test_validate_migration_ordering.py | 657 +++++++++++++++++++++++-
 tools/validate_migration_ordering.py            | 225 +++++++-
 3 files changed, 889 insertions(+), 21 deletions(-)
```

`run_regression.py` → **FAIL (5/6, 1 N/A)**. Both migration-ordering checks
PASS (`all 36 tests passed`). The single FAIL is the **pre-existing,
unrelated** `evidence_integrity_check.py` `CURRENT_HANDOFF.md` staleness,
identical to `RUN_20261004T114858Z.txt` from before this session began;
clearing it requires a **commit**, which this session is forbidden to make.
This round's record: `RUN_20261004T132510Z.txt`.

---

## 6. Mutation battery — 11 → 13, all killed

```
m0 baseline (unmutated): SANE — unit exit 0, PASS — all 36 tests passed (discovered dynamically, not hand-listed).
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
M12 UNREADABLE_RECORDS_PATH report suppressed (R3-1 guard removed): KILLED by unit
M13 enumerator reverted to error-suppressing rglob (R3-1 root cause restored): KILLED by unit

real tool sha256 unchanged:  5738c9510904b0e80c2730ce4e1b97a2e7935289951a13084729b58254c0539e
real test sha256 unchanged:  10c2872be3eb0aa5ce4b28416444c9b6ad56a09e94877143a3dd88259814f37c
13/13 mutations killed; survivors=[]
```

**M1-M11 kill signals are identical to round 2's** — the prior battery is
preserved, not merely re-asserted.

Two round-3 mutants, deliberately distinct: **M12** keeps the explicit walk
but silences its error report (someone deletes the guard); **M13** reverts
the enumerator itself to `rglob` (the literal pre-fix state round 3
reproduced). A fix that only M12 caught would still be architecturally
reversible in one line. Because the kill is driven by the *injected* tests,
both die deterministically regardless of host permissions.

### Harness correction, recorded not hidden

**M6's anchor broke, and the harness refused the whole run rather than
reporting a kill it had not performed:**

```
INVALID: anchors not matching exactly once: ["M6 discovery narrowed back to glob('*.yaml') (R1-3 fix removed)"]
EXIT=2
```

M6 was anchored on `discover_records`'s `for path in sorted(records_dir.rglob("*")):`
line, which this remediation removed. Re-anchored to the new seam
(`entries, problems = enumerate_tree(records_dir)` →
`sorted(records_dir.glob("*.yaml")), []`), preserving M6's original semantics
— narrow enumeration so non-`.yaml` and nested files are silently ignored
again — and its original `KILLED by unit` signal. This is the second time the
anchor-uniqueness assertion has caught real drift (round 2 caught M7's); it
is the control working, but it also means **every mutation anchor is coupled
to code shape and must be re-validated whenever the enumerator changes.**

---

## 7. Limitations and remaining gaps — stated, not closed

1. **R3-1's named shape is closed; "exhaustive discovery" is now an
   enumerator property rather than a claim.** What is *not* proven is that no
   other stdlib call in this tool suppresses errors. `read_text` still
   raises (see 2), `is_dir`/`is_symlink`/`stat` can each raise `OSError` on a
   hostile tree; `enumerate_tree` guards its own `scandir` and `is_dir`, but
   `discover_records`'s `path.is_symlink()` and `validate_directory`'s
   `records_dir.is_dir()` are unguarded. On a tree where those raise, the
   tool dies with a traceback — **fail-closed (nonzero), not fail-open**, but
   not a named problem.

   > **CORRECTION, 2026-10-04 (round-4 finding R4-2, appended by the round-4
   > root-cause remediation session — the original text above is kept as the
   > historical record, per this project's append-not-rewrite convention).
   > The claim in the last sentence of item 1 is FALSE, and false in the
   > reassuring direction.** `Path.is_dir()`, `Path.exists()` and
   > `Path.is_symlink()` do **not** raise on `OSError`; they catch it and
   > return `False`. So the consequence was not "dies with a traceback,
   > fail-closed" — it was a **fail-open**: round-4's independent review
   > reproduced a records directory holding a destructive out-of-order
   > `contract` behind a mode-000 **parent** producing exit **0**, the
   > ordinary `PASS` line, and a NOTICE affirmatively stating the directory
   > "does not exist", on the default invocation that
   > `knowledge/05-QA/tools/run_regression.py` actually makes. This session
   > independently re-reproduced that same output before fixing it (see
   > `SCN070-ROUND4-ROOT-CAUSE-REMEDIATION-2026-10-04.md` §3).
   >
   > The error was one of method, not of honesty: this consequence was
   > **reasoned about rather than executed**, in the one item of this record
   > that addressed the surviving defect's actual location — which is
   > precisely the sentence a governance reader would rely on when judging
   > whether the root cause had been eliminated. It is also why item 1's
   > self-description as "the honest boundary of what was proven" (see the
   > closing paragraph of this section) drew that boundary in the wrong
   > place. The defect is fixed as of the round-4 remediation; this
   > correction stands regardless, because the record itself was wrong.
2. **R2-4 residual, unchanged.** An unreadable *record file* (mode 000) and a
   non-UTF-8 record still die with `PermissionError`/`UnicodeDecodeError`
   tracebacks rather than named problems. Round 3 re-confirmed both exit 1,
   so they are fail-closed and remain the carried-forward P3 they were. The
   one-line widening (`except (RecordError, OSError, UnicodeDecodeError)`)
   was **not** applied — out of this round's authorized bound, which is R3-1
   only.
3. **R3-2 (P3) not fixed** — unknown front-matter keys are still silently
   ignored, so a decoy `Phase:`/homoglyph key can show a reader a different
   phase than the one enforced. Round 3 and the convergence assessment both
   record no ordering bypass. Carried, not closed.
4. **R3-3 (P3) not fixed** — absolute host paths still printed, including in
   the new `UNREADABLE_RECORDS_PATH` message for the root case. CI-log
   hygiene only. Nested directories are named relatively, so the new message
   does not widen this.
5. **R3-4 (P3) not fixed** — no `.github/workflows` exists (re-verified).
   The lint and its suite are registered in `run_regression.py` only;
   `--require-dir` is still not passed there, and the real tree is still
   vacuous (`records/` holds only `.gitkeep`, legitimate per GOV-01-R06's own
   OUT-of-scope line). Real CI remains a GOV-01-R04 obligation.
6. **`IGNORED_NON_RECORD_FILES` limitation, unchanged.** A file literally
   named `.gitkeep` or `.DS_Store` with record-shaped content is skipped.
7. **Mutation anchors are shape-coupled** — see §6's M6 correction. A future
   structural change must re-run the battery and expect exit 2, not assume
   13/13 still anchors.
8. **Mutation score is not a scenario PASS.** 13/13 proves each listed
   mutation is detected by a durable control; it says nothing about defects
   outside the set.
9. **Observed discrepancy in the round-3 report, not corrected by this
   session.** §4 of that report states `HEAD = 3552299`; actual `HEAD` is
   `e481b814a80923849dddfe7a49319112aae7b023` (`e481b81`), which is what the
   convergence assessment records and what `git rev-parse` returns now. The
   report is an independent review artifact and was left unmodified; flagged
   here for the reconciliation step rather than edited.

**Honest statement on convergence:** this round changed the enumerator
abstraction the convergence assessment identified, and both the named R3-1
shape and the previously-unprobed nested-subtree variant now fail closed with
named problems. Whether that "demonstrably eliminates the root cause" in the
assessment's sense is a reconciliation judgment for governance — **this
session does not make it, and does not modify convergence status.** Item 1
above is the honest boundary of what was proven.

> **ANSWERED, 2026-10-04 (appended by the round-4 root-cause remediation
> session).** Governance made that judgment: it does **not**. Round 4's
> independent review found a same-invariant fail-open surviving this
> remediation (R4-1), the `NON_CONVERGING` condition was met on the
> convergence assessment's own terms, and
> `SCN070-ROUND4-ROOT-CAUSE-ASSESSMENT-2026-10-04.md` authorized one further
> bounded cross-layer remediation — metadata acquisition, traversal and
> notice from a single authoritative result — which is recorded in
> `SCN070-ROUND4-ROOT-CAUSE-REMEDIATION-2026-10-04.md`. See also the
> CORRECTION under item 1 above: this section's own statement of what
> remained unproven was itself factually wrong.

---

## 8. Integrity / fail-closed compliance

- **No commit, push, stash, reset, checkout, discard, or branch change.**
  `git rev-parse --short HEAD` = `e481b81`, unchanged across all three rounds.
- **No deletions or renames** — `git status --porcelain | grep -E "^( D|D |R )"`
  returns nothing. Porcelain count 328 → 329 (this record is the +1).
- **Files this round touched — exactly four:**
  1. `tools/validate_migration_ordering.py` — SHA-256 `5738c9510904b0e80c2730ce4e1b97a2e7935289951a13084729b58254c0539e`
  2. `tools/tests/test_validate_migration_ordering.py` — SHA-256 `10c2872be3eb0aa5ce4b28416444c9b6ad56a09e94877143a3dd88259814f37c`
  3. `knowledge/03-Modules/MOD-001/evidence/implementation/scn070_ordering_lint_mutation_killcheck.py` — SHA-256 `7aa1a487555f91c4b5b197516368faef6f7c2c16a8de11d95ccdc2bcb96cf213`
  4. This record (new).
  `backend/migrations/TEMPLATE.md` was **not** re-edited this round (R3-1 is
  not an authoring rule — a records dir becomes unreadable by ownership or
  mount, not by how an author writes a record).
- **Not touched:** `SCN070-CONVERGENCE-ASSESSMENT-2026-10-04.md`,
  `REVIEW_IN_FLIGHT.md` (read only — its `M` status in `git status` predates
  this round; the watchdog wrote the round-3 claim), `SCENARIOS.md`
  (SCN-MOD001-070 still reads `EXECUTED — PENDING INDEPENDENT REVIEW
  (2026-10-04)`, verified), `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`,
  `REQUIREMENTS.md`, every `.claude/` file, all four governing baselines, and
  **every DOM-002 artifact** (round 5 remains interrupted/non-resumable; not
  read for verdict, not resumed, not dispatched).
- **No reviewer launched, no self-approval, no promotion, no certification,
  no convergence-status change.**
- **All pre-existing uncommitted work preserved** — count only grew; nothing
  reverted.
- **Owner-reserved absolutes respected:** no spend, no paid service, no real
  member data (all fixtures synthetic), no deploy/Production promotion, no
  material product/pricing/business/architecture/scope change. *(The
  enumerator replacement is internal to one `tools/**` validator under an
  explicit governance authorization — not a product-architecture change.)*
- **Throwaway fixtures deleted at closeout:** `/tmp/scn070_r3fix/` removed
  (modes restored to 0700 before deletion), absence confirmed; the kill-check
  removes its own `tempfile` mirrors in `finally` and asserts the real tool's
  and test file's SHA-256 unchanged in `finally`, at interpreter exit, and on
  SIGINT/SIGTERM.

## 9. Next legal action

Per the convergence assessment: **reconcile this record's exact evidence and
separately decide** whether a distinct new P2 justifies one exceptional
review within the five-review absolute cap — a fourth review is not
pre-authorized. If this remediation does not demonstrably eliminate the root
cause, or introduced another same-invariant fail-open, the assessment directs
marking `NON_CONVERGING` rather than cycling. §7 item 1 is the honest
boundary to weigh. SCN-MOD001-070 stays `EXECUTED — PENDING INDEPENDENT
REVIEW`. No DOM-002 dispatch is permitted.

---

## CORRECTION (appended 2026-10-05) — the two citations to `SCN070-ROUND4-ROOT-CAUSE-REMEDIATION-2026-10-04.md` dangle

Round-5 finding **R5-2**
(`knowledge/03-Modules/MOD-001/evidence/security/SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND5-2026-10-04.md`
§7) found that this record cites
`SCN070-ROUND4-ROOT-CAUSE-REMEDIATION-2026-10-04.md` twice — at **line 335**
(*"This session independently re-reproduced that same output before fixing
it (see … §3)"*) and at **line 397** (*"which is recorded in …"*) — and that
**the cited file does not exist and was never written.**
`SCN070-ROUND4-ROOTCAUSE-WATCHDOG-CHECKPOINT-2026-10-04.md:3` records why:
the implementing ACPX turn *"stopped before a final response or
implementation report."*

**Both citations should now be read as pointing to**
`knowledge/03-Modules/MOD-001/evidence/implementation/SCN070-ROUND5-ROOTCAUSE-IMPLEMENTATION-2026-10-05.md`
— specifically its §6, which reconciles the round-4 evidence gap and pins
the bytes (`8f3d166b…` / `2ad9dc35…` / `90b7c3ef…`) that round 5 reviewed.

Three things that correction does **not** do, stated so this block is not
read as more than it is:

1. **It does not create the cited filename.** A file named
   `…ROUND4-…-2026-10-04.md`, authored on 2026-10-05 by a session that did
   not perform round-4's work, would resolve the citation by manufacturing
   a record that misstates its own date and authorship — the R5-2 defect
   class, not its remedy.
2. **It does not validate the sentence the line-335 citation supports.**
   *"This session independently re-reproduced that same output before fixing
   it"* was a claim about the round-4 implementing session, and no durable
   record of that session's execution exists. Round 5 judged the claim
   **credible but untraceable** (its §8: *"the claim is credible and the
   correction stands; the trail to it does not"*), having re-established the
   fail-open's existence indirectly via its own MUT-R5-A reversion. It
   remains credible-but-untraceable. The 2026-10-05 session did not observe
   round-4's execution either and does not attest to it.
3. **It does not alter anything above.** Per this project's
   append-not-rewrite convention, the original text — including both
   dangling citations and this record's own superseded SHA-256 values in §8,
   which correctly describe *round 3's* bytes — is retained verbatim. Those
   hashes are superseded, not wrong.

The technical content of the earlier CORRECTION under §7 item 1 was
independently assessed as accurate with no residual overclaim (round-5
report §8). This appended block concerns its citation only.

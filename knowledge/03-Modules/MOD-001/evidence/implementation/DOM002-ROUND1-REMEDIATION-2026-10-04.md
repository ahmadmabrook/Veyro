---
doc: DOM002_ROUND1_REMEDIATION
status: FINAL
module: MOD-001
requirement: GOV-01-R02 (CONC category) — DOM-002 optimistic-concurrency/versioning test pattern
responds_to: knowledge/03-Modules/MOD-001/evidence/code-review/DOM002-CONCURRENCY-PATTERN-CODE-REVIEW-ROUND1-2026-10-04.md
remediation_session: same retained MOD-001 GOV-01-R02 implementation session (Sonnet), not an independent review
date: 2026-10-04
---

# DOM-002 concurrency pattern — round-1 code-review remediation

## 0. What this is

Bounded remediation of the two files round 18 created
(`backend/tests/harness/concurrency.py`,
`backend/tests/integration/test_concurrency_harness.py`) against the
independent round-1 code review's verdict **BLOCKED (P0=0, P1=2, P2=2,
P3=6)**, orchestrator-verified `mr_verify.py` PASS 104/104 `claude-opus-5`.
This is implementation remediation, not a self-approval of the fix — see
§6 for the next independent-review action.

## 1. P1-1 — shared unowned schema clobbering tenant-isolation ownership

**Fix:** the concurrency harness now creates its own `concurrency_harness`
schema, never the `"harness"` schema `tenant_isolation.py` owns, with an
explicit `AUTHORIZATION <superuser>` clause making ownership deterministic
regardless of call order (`concurrency.py`'s `create_versioned_table`).
No code change was made to `tenant_isolation.py` or any other file outside
the two originally-reviewed files plus the new regression file below.

**Verification:** review §4.4's exact drill re-run —

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py \
      "tests/integration/test_architecture_gate_rls.py::test_p1_canonical_harness_passes" -q
5 passed in 1.90s
```

No `InsufficientPrivilege`. Also confirmed in a throwaway full-structure
copy (`backend/` + `tools/` mirrored under `/tmp`, deleted after) that
*reintroducing* the old shared-schema/no-teardown code reproduces the
review's exact `psycopg.errors.InsufficientPrivilege: permission denied
for schema harness` under the same drill — i.e. the fix is load-bearing,
not coincidental.

## 2. P1-2 — persistent unclassified table failing the ADR-010 RLS gate

**Fix:** `_widget_table` (session-scoped autouse, never torn down) is
removed. The `widget` fixture in `test_concurrency_harness.py` now creates
the table, yields the row id, and drops the table on every single test via
`drop_versioned_table` — the relation never persists past one test, so no
RLS-gate invocation anywhere in the same session can observe it.

**Verification:** review §4.5's exact drill re-run —

```
$ .venv/bin/python -m pytest \
      "tests/integration/test_architecture_gate_rls.py::test_p1_canonical_harness_passes" \
      tests/integration/test_concurrency_harness.py \
      "tests/integration/test_architecture_gate_rls.py::test_p4_p5_p6_manifest_platform_table_sequence_and_reviewed_definer" -q
6 passed in 2.07s
```

No `RLS_TABLE_UNCLASSIFIED`. Reintroducing the old fixture shape in the
same throwaway copy as §1 reproduces the review's exact failure mode (gate
goes red / errors when the concurrency module runs between two gate
invocations).

## 3. Permanent order-independence regression coverage (new)

New file: `backend/tests/integration/test_concurrency_harness_order_independence.py`
— two tests, each shelling out to a fresh `pytest` subprocess with the
review's own §4.4/§4.5 orderings and asserting exit code 0. This makes the
two manual drills above permanent and automated rather than one-off:

```
$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness_order_independence.py -v
test_concurrency_before_canonical_rls_harness_test_review_4_4   PASSED
test_concurrency_between_two_rls_gate_invocations_review_4_5    PASSED
2 passed in 4.47s
```

**Not vacuous — proven by reintroducing the pre-fix defect shape** (shared
`"harness"` schema + session-scoped no-teardown fixture) in a throwaway
full-structure copy and re-running this exact file:

```
FAILED test_concurrency_before_canonical_rls_harness_test_review_4_4
FAILED test_concurrency_between_two_rls_gate_invocations_review_4_5
2 failed in 4.20s
```

(Real repo files were never touched by this drill — confirmed via
`git status --porcelain` on the three files before/after, unchanged.)

## 4. P2-1 — missing-row conflated with version-conflict

**Fix:** new typed `RowNotFound` exception. `update_versioned` now runs a
narrow `SELECT EXISTS(...)` check only when the version-checked `UPDATE`
affects zero rows, raising `RowNotFound` for a genuinely missing row and
`VersionConflict` only when the row exists but its version moved. New test
`test_update_versioned_distinguishes_missing_row_from_version_conflict`.

**Verification — mutation M6** (remove the existence check, always raise
`VersionConflict`) **killed**:

```
FAILED test_update_versioned_distinguishes_missing_row_from_version_conflict
E   tests.harness.concurrency.VersionConflict: version conflict on ...
```

## 5. P2-2 — test 3's "identical two-writer shape" claim was inaccurate

**Fix:** `test_naive_unversioned_update_loses_the_update` rewritten to use
the genuinely identical precondition `test_concurrent_writers_lost_update_detected`
uses (both writers read the same starting version), exactly the shape the
original review's own §4.6 PROBE3 demonstrated works. Writer A commits via
the real `update_versioned`; writer B, still holding its stale read, goes
through `update_unversioned_blind` and silently overwrites writer A's
committed change. Both docstrings corrected to describe this accurately.
Added assertion (addresses **P3-1** in the same edit): the final `version`
column equals `writer_a_version + 1` while the value is writer B's — a
concrete demonstration that the version column itself becomes a false
positive once an unversioned write slips through, not just a value
overwrite.

## 6. P3s: dispositions

- **P3-1 (blind path's staleness never asserted):** FIXED, folded into §5's rewrite.
- **P3-2 (mutation-sensitivity claim unevidenced):** ACKNOWLEDGED, evidence now exists twice over — the original review's own §4.7 (5/5 killed) and this remediation's own re-run (M1/M2/M5/M6, 4/4 killed, plus the order-independence drill in §3). No permanent automated mutation-testing harness added; judged disproportionate cost for a bounded remediation pass. No repo change beyond the evidence in this file.
- **P3-3 ("racing writers" unqualified in STATUS.md/SCENARIOS.md):** FIXED — `SCENARIOS.md`'s `SCN-MOD001-009` entry now has an added paragraph pointing at the harness's own "Known ceiling" section; `STATUS.md`'s round-18 entry is left as historical record per this project's append-don't-rewrite convention, with the round-2 entry (this remediation) stating the qualifier explicitly.
- **P3-4 (`one_row`/`Conn` duplicated vs. `tenant_isolation.py`):** FIXED — one-line comment added above the re-declaration in `concurrency.py` explaining the deliberate zero-dependency decoupling, per the review's own "if so, say so in a comment" suggestion.
- **P3-5 (control-4 decision only in a rotating front-matter line):** FIXED — the reject-and-retry decision is now also recorded durably and non-chronologically in `REQUIREMENTS.md`'s own `DOM-002` traceability row.
- **P3-6 (two robustness nits — `AssertionError` elided under `-O`; `IF NOT EXISTS` masking a shape mismatch; no placeholder/param-count check):** ACKNOWLEDGED, no code change. `AssertionError`-under-`-O` is the same idiom `tenant_isolation.py` already uses (consistent, not a regression this file introduces). `IF NOT EXISTS`'s masking risk is now much lower than at review time: the table lives in an exclusive schema only this harness ever creates, is dropped after every test, and the container is fresh per session — no realistic path to a leftover wrong-shape table remains. The placeholder/param-count footgun has no real caller today (only this file's own tests call `update_versioned`/`update_unversioned_blind` with literal, matched tuples); adding runtime validation for a scenario no current caller can trigger was judged not worth the complexity for this bounded pass — flagged here for whoever adds the first real caller to reconsider.
  **Correction (round 2, 2026-10-04):** round-2 code review finding R2-2
  demonstrated this disposition's "no realistic path to a leftover
  wrong-shape table remains" claim was wrong — a setup failure in `widget`
  between `create_versioned_table` and `yield` (then: no `try`/`finally`)
  did leak the table for the rest of the session, reproduced live in the
  review's own §4.11 drill. That specific path is now closed by R2-2's fix
  (see `DOM002-ROUND2-REMEDIATION-2026-10-04.md` §2) — the `widget` fixture
  now wraps everything from the create through the `yield` in
  `try`/`finally`. The `-O` and param-count halves of this disposition
  stand uncorrected; only the `IF NOT EXISTS` half's reasoning was wrong.

## 7. Full regression evidence

```
$ .venv/bin/python -m ruff check .                     # whole backend tree
All checks passed!

$ .venv/bin/python -m mypy tests/ --strict             # (pyproject.toml already sets strict)
Success: no issues found in 28 source files

$ .venv/bin/python -m pytest tests/integration/test_concurrency_harness.py -v
4 passed in 1.62s

$ .venv/bin/python -m pytest tests -q                  # default (alphabetical) order
202 passed in 27.36s

$ .venv/bin/python -m pytest $(find tests -name "test_*.py" | sort -r) -q   # reversed order
202 passed in 28.18s
```

202 = 199 (round-18 baseline) + 1 new missing-row test (§4) + 2 new
order-independence regression tests (§3). Zero regressions in either
collection order.

## 8. Scope discipline confirmed

No edit to `R04`, `ADR-010`, `SCN-067`, `BUG-048`. `SCN-MOD001-009` is
**not promoted and not claimed PASS** by this remediation. Files changed
this round: `backend/tests/harness/concurrency.py` (rewritten),
`backend/tests/integration/test_concurrency_harness.py` (rewritten), new
`backend/tests/integration/test_concurrency_harness_order_independence.py`,
plus durable-record edits to `SCENARIOS.md`, `REQUIREMENTS.md`,
`STATUS.md`, `TEST_RESULTS.md`, `CURRENT_STATE.md`, `CURRENT_HANDOFF.md`,
and this evidence file. No commit/push — all new/changed files remain
either untracked or part of this session's existing uncommitted set; no
pre-existing uncommitted work was reset, stashed, or discarded.

## 9. Next independent-review action

A second independent fresh-context Opus code review should re-run this
report's §1-§5 commands directly (not re-derive them) and confirm: the
schema-ownership contract actually holds under order the first review
didn't try (e.g. `pytest -p xdist` random order, if that plugin is ever
added), the `RowNotFound`/`VersionConflict` distinction is itself
correctly typed at every call site, and that the P2-2 rewrite's "identical
shape" claim is now actually true (re-read §5's diff, don't just trust
this file's prose). `REVIEW_IN_FLIGHT.md`'s round-1 claim should already be
`CLEAR` per that review's own §9 item 5; this remediation did not touch
that file and leaves it as found.

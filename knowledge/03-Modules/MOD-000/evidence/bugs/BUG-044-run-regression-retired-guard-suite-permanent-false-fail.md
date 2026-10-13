---
doc: BUG-044
status: CLOSED — 2026-10-01 independent Opus recovery assurance
---

# BUG-044 — `run_regression.py` runs the retired CAP-007 guard suite as a current permanent gate, guaranteeing permanent FAIL; 3 records still described it as a live passing gate

**Module:** MOD-000 (tool: `knowledge/05-QA/tools/run_regression.py`,
plus documentation drift in `TEST_RESULTS.md`, `REGRESSION_INDEX.md`,
`CAPABILITY_REGISTRY.md`)
**Severity:** P1 (a permanent regression gate that can never pass again
for a known, owner-authorized reason either blocks all future work or
trains sessions to ignore its FAIL verdicts — both are real governance
risks, not cosmetic)
**Status:** CLOSED — 2026-10-01 independent Opus recovery assurance. Fixed
2026-10-01, same session as filing, Sonnet-tier recovery remediation.
**Corrected 2026-10-01 (independent Opus recovery review, session
`veyro-recovery-opus-gate-20261001`, model `claude-opus-5-5`): this file
originally said CLOSED — overclaimed. The fix itself was technically
re-verified by that review (part of a 38/38 pass across BUG-043/044/045's
combined test suites, plus validators), but the review's overall verdict
was BLOCKED specifically because this file's and `BUG_REGISTRY.md`'s
CLOSED language was itself a premature-completion finding — a Sonnet-tier
local fix is not a closure until a fresh independent assurance pass
approves it as such. That BLOCKED finding was superseded by the same independent Opus session's targeted re-review at 2026-10-01 11:33:47 UTC: APPROVED, P0=0/P1=0. This is recovery assurance only, not CAP-008 qualification or an R04 gate. **Batch 7 attribution correction (2026-10-01):** The later claim that this reviewer re-confirmed BLOCKED on a totals inconsistency was erroneous; the saved ACPX history records APPROVED at 11:33:47 UTC. Earlier BLOCKED text above remains as historical sequence. Model attestation:
reviewer's model attestation PASSED `mr_verify.py` (genuine Opus
transcript, 51 turns); grounded in `DC-06` ("no self-approval" — a
reviewer/Gatekeeper runs in a fresh context separate from the
implementing session) — the Sonnet session that fixed this bug cannot
be the one that closes it. See
`knowledge/05-QA/BUG_REGISTRY.md`'s front matter for the corrected
aggregate totals this finding also required.

## Summary

`OWN-006`/`ADR-007` retired CAP-007 (2026-09-28, commit `058ed27`):
`bash_guard.py`'s enforcement logic was replaced with an inert allow-stub
and its `PreToolUse` hook removed from `.claude/settings.json`. Its own
194-test regression suite, `.claude/security/tests/test_bash_guard.py`,
correctly and permanently now fails 149/194 — it tests enforcement
behavior that was deliberately and authorizedly removed, not a real
regression.

`knowledge/05-QA/tools/run_regression.py` still ran that suite
unconditionally as one of 5 checks feeding a single aggregate pass/fail
verdict, with no way for the aggregate to ever report PASS again. Three
durable records still described the suite in the present tense as a
live, passing, or allowlist-pending regression gate:

1. `knowledge/03-Modules/MOD-000/TEST_RESULTS.md` — row labeled "(current)"
   with "PASS, 194/194 (re-confirmed Phase 8/9)".
2. `knowledge/05-QA/REGRESSION_INDEX.md` — "Current state" prose wrapping
   the suite into the aggregate with no caveat, plus a closing sentence
   "`test_bash_guard.py`... remains, on its own, a real, permanent,
   automated regression suite... re-run clean at every checkpoint."
3. `knowledge/00-System/CAPABILITY_REGISTRY.md`'s snapshot-section
   "Activation gap, disclosed" note — described `capability_drift_check.py`
   as "not yet on `bash_guard.py`'s trusted-script allowlist" in the
   present tense, which presumes a live, enforcing guard with an
   allowlist to be added to; no such guard currently exists.

## Fix

`run_regression.py`: added `retired_capability_ids()` (reuses
`capability_drift_check.py`'s `parse_retired_capabilities()` against the
live registry text — not a copy of that regex) and
`RETIRED_SUITE_FOR_CAPABILITY = {"test_bash_guard.py": "CAP-007"}`.
`run_all()` now checks, on every run, whether the suite's gating
capability is currently marked RETIRED in `CAPABILITY_REGISTRY.md`; if
so, the suite is not executed at all and is reported `N/A (RETIRED)`,
excluded from `all_pass` and the X/Y tally, with the finding text citing
`OWN-006`/`ADR-007`. This is read dynamically from the registry, not
hardcoded — if CAP-007's retirement marker is ever removed/superseded
(i.e. reinstated), the suite automatically resumes running and gating
normally with no code change required. Explicit rollback instruction
recorded in code comments, `TEST_RESULTS.md`, and `REGRESSION_INDEX.md`:
all 194 tests must pass again before the suite may be treated as a live
gate if CAP-007 is reinstated.

All three named records corrected with dated annotations citing
`OWN-006`/`ADR-007`, preserving their original historical PASS text
rather than deleting it (it was true when written).

Swept `knowledge/` for other `194/194`/`test_bash_guard` mentions: all
remaining ones are already-dated historical narrative (bug closure
records, phase/certification reports, slice implementation records)
correctly describing real past events in past tense — no further live
current-state contradiction found.

## Verification

`run_regression.py` run for real: before this fix, the aggregate would
have reported FAIL permanently (4/5 real checks PASS, `test_bash_guard.py`
FAIL) with no way to ever reach PASS again. After: **exit 0, AGGREGATE
RESULT: PASS (4/4 checks passed, 1 N/A excluded)**, record written to
`knowledge/05-QA/tools/regression-runs/RUN_20261001T064138Z.txt`.

New `knowledge/05-QA/tools/test_run_regression.py` — 6/6 pass: retired
capability excludes its suite as N/A (positive, the core fix); N/A result
not counted in `all_pass` or the tally; **reinstated capability (simulated
by an empty retired-set) resumes real execution and fails closed on both
a real failure and a real pass** (2 cases proving the rollback-instruction
claim is enforced by code, not just documented); only the one named
mapping (`test_bash_guard.py` → `CAP-007`) is retirement-eligible, an
unrelated check still fails closed regardless of unrelated retirements;
`retired_capability_ids()` reads the live registry and finds CAP-007
there today.

Also re-run clean after this fix: `evidence_integrity_check.py` (exit 0),
its tests (6/6), `capability_drift_check.py` (exit 0, 8/8, 0 errors), its
tests (12/12), `verify_baselines.py` (4/4 PASS), `validate_capabilities.py`
(7/7 PASS), capability manifests for MOD-000 (7/7) and MOD-001 (9/9) both
PASS. `git rev-parse HEAD` == `origin/main`, unchanged — uncommitted
working-tree edit only.

## Scope note

The 194-test suite itself is unmodified — this fix changes how its
*result* is scored by the aggregate harness, not the suite's own content
or `bash_guard.py`. Does not reactivate CAP-007, does not touch CAP-008
or `BUG-038`.

## Final independent closure — 2026-10-01

Fresh independent `claude-opus-5-5` review session `veyro-recovery-opus-gate-20261001` returned **APPROVED**, P0=0/P1=0, after its initial BLOCKED verdict and the records-only remediation. Runtime model attested by `mr_verify.py`; 38/38 focused tests and validators passed in the review copy. This closes this recovery defect, not CAP-008 or BUG-038. Earlier pending/blocked statements above are historical and superseded by this final verdict.

## Final independent closure correction — 2026-10-01

The independent fresh-context Opus session `veyro-recovery-opus-gate-20261001` gave a targeted final verdict **APPROVED, P0=0/P1=0** at 11:33:47 UTC after reviewing the corrected status records. `mr_verify.py` attested `claude-opus-5-5`; 38/38 focused tests and validators passed in its earlier technical pass. The subsequent Batch 7 phrase “re-confirmed BLOCKED” misattributed a verdict that never occurred; the later `veyro-recovery-opus-after-b6-20261001` review identified that records error. Current status is CLOSED on this independent approval, not Sonnet self-approval. CAP-008 and BUG-038 remain separate and unapproved.

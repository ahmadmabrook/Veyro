---
doc: BUG-019
status: FIXED (2026-09-06)
found_date: 2026-09-06
found_by: Phase 7 fresh-context Opus veyro-security-reviewer (SEC-12) AND veyro-performance-reviewer (RES-01), independently, same finding
severity: P2
---

# BUG-019: `evidence_integrity_check.py` PASSes in the working copy but FAILs in a fresh clone

## What is wrong

Both Phase 7 reviewers independently found the same real defect: the
checker prints `PASS` in the working tree and `FAIL — 6 finding(s)` in a
fresh `git clone` of the identical commit. All six are
`BROKEN REFERENCE ... '.claude/settings.local.json' does not exist`, from
6 durable evidence files. The file is correctly gitignored and correctly
untracked (confirmed via `.gitignore` and `git ls-files`) — a real
disaster-recovery session that clones and runs this checker as directed
would get a false BLOCKED on a deliberately local-only artifact, and
Phase 9's fresh-session restoration proof would hit this unexplained.

## Remediation applied (2026-09-06)

Added a distinct `EXPECTED_LOCAL_ONLY` set (separate from
`EXPECTED_NOT_YET_CREATED` — the semantics differ: this path is correct
to *never* exist in a clone, not a forward reference that will exist
later) containing `.claude/settings.local.json`, routed to the same
non-blocking `expected_absent` reporting path.

**Live-verified:** cloned the real repo fresh, copied the fixed checker
in, ran it against the clone's actual file tree (settings.local.json
confirmed absent, as in any real clone) — `PASS`, the 6 findings now
correctly reported as expected-absent rather than broken references.

## Certification impact

Does not block Phase 7 (P2, now fixed) — but would have blocked Phase 9
if left unfixed, since Phase 9's fresh-session restoration proof clones
and runs this exact checker.

## Affected

`knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/tools/
evidence_integrity_check.py`, and (as forward-looking documentation, not
yet written) Phase 9's restoration proof.

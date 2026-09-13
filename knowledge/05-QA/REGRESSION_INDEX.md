---
doc: REGRESSION_INDEX
status: LIVE — no permanent, CI-wired automated regression suite exists yet for the catalog level (known gap, SCN-091 BLOCKED); the Bash-guard surface specifically now has one (194 tests)
updated: 2026-09-13 (Phase 9 restoration proof, third Gatekeeper pass Editorial — "Phases 1-5" corrected to "Phases 1-8", stale since this file's own 2026-09-12 update)
---

# Permanent Regression Suite Index

Appendix D field: "Permanent regression suite and latest pass evidence."

**Honest current state:** no permanent, automated regression suite exists
yet for MOD-000. This is one of the EIP §21.1-mandated MOD-000 outputs
that remains genuinely unauthored (the same gap the catalog's SCN-091
"permanent-regression automation harness" tracks as BLOCKED/artifact-pending
since Phase 1 — required before Phase 10 certification).

**What exists instead (manual re-verification, not automated regression):**
`validate_catalog.py` and `evidence_integrity_check.py`
(`knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/tools/`
and `scenario-catalog/tools/`) are re-run by hand after every material
change and have been re-run clean dozens of times across Phases 1-8. This
is real, repeated verification — but it is not a "permanent suite" in the
EIP's sense (not CI-wired, not automatically triggered).

This file will carry real pass-evidence links once SCN-091's harness is
authored.

## Update (2026-09-12, Phase 8 closeout reconciliation)

`.claude/security/tests/test_bash_guard.py` (194 tests) IS a real,
permanent, automated regression suite for the Bash-surface security
guard specifically — re-run clean at every checkpoint across Phases
7-8, most recently as part of this chunk's own closeout. This is
narrower in scope than SCN-091's own ask (a catalog-wide, CI-wired
harness covering all 95 scenarios), which remains genuinely unauthored
and correctly BLOCKED (artifact-pending, required before Phase 10). Not
conflating the two: the Bash guard's suite closes one real slice of this
gap, not the whole of it.

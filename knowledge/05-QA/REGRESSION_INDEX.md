---
doc: REGRESSION_INDEX
status: LIVE — no permanent automated regression suite exists yet (known gap)
updated: 2026-09-05
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
change and have been re-run clean dozens of times across Phases 1-5. This
is real, repeated verification — but it is not a "permanent suite" in the
EIP's sense (not CI-wired, not automatically triggered).

This file will carry real pass-evidence links once SCN-091's harness is
authored.

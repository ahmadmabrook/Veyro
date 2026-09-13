---
doc: REGRESSION_INDEX
status: LIVE — permanent regression harness authored 2026-09-13 (SCN-091 PASS); not yet CI-wired (no CI infrastructure exists on this project, out of MOD-000 scope)
updated: 2026-09-13 (Phase 10 readiness — SCN-091 closed: knowledge/05-QA/tools/run_regression.py authored, wrapping all 5 permanent checks into one aggregate command with a durable pass record)
---

# Permanent Regression Suite Index

Appendix D field: "Permanent regression suite and latest pass evidence."

**Current state:** `knowledge/05-QA/tools/run_regression.py` (authored
2026-09-13, Phase 10 readiness) is the permanent, automated regression
harness for MOD-000's control-plane checks. It wraps `verify_baselines.py`,
`validate_catalog.py`, `validate_capabilities.py`,
`evidence_integrity_check.py`, and `.claude/security/tests/test_bash_guard.py`
into one command, reports one aggregate pass/fail result, and writes a
timestamped, durable pass record under
`knowledge/05-QA/tools/regression-runs/`.

**Honest scope note:** this is a local aggregator, not a CI-wired
pipeline — no CI infrastructure exists on this project, and standing
one up is out of MOD-000's control-plane-bootstrap scope (and would
likely touch owner-reserved territory: a CI provider is an external
service). It is fully runnable today by the owner or any human terminal
session. It is not yet on `.claude/security/bash_guard.py`'s
trusted-script allowlist, so an agent session cannot invoke it directly
through its own governed Bash tool — that specific activation step
requires an owner-authorized edit to `.claude/security/**` plus an
independent security re-review, the same discipline every prior change
to that file has gone through. See
`knowledge/05-QA/tools/regression-runs/RUN_2026-09-13_phase10_readiness.md`
for the first real pass record (all 5 constituent checks run
individually and confirmed passing, since the wrapper itself could not
be executed under this session's own tool access).

`.claude/security/tests/test_bash_guard.py` (194 tests) remains, on its
own, a real, permanent, automated regression suite for the Bash-surface
security guard specifically — re-run clean at every checkpoint across
Phases 7-10.

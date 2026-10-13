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
into one command and writes a timestamped, durable pass record under
`knowledge/05-QA/tools/regression-runs/`. **Corrected 2026-10-01
(`BUG-044`):** the `test_bash_guard.py` entry is no longer unconditionally
scored into the aggregate pass/fail — since CAP-007's enforcement was
retired 2026-09-28 (`OWN-006`/`ADR-007`, commit `058ed27`), that suite now
correctly and permanently fails 149/194 testing behavior that was
deliberately removed, which would make the aggregate FAIL forever for a
known, owner-authorized reason rather than a real regression. The script
now reads `CAPABILITY_REGISTRY.md`'s live retirement marker on every run
and reports this one entry `N/A (RETIRED)`, excluded from the pass/fail
tally, instead of running it as a gate it can no longer pass. This is
read dynamically, not hardcoded — if CAP-007 is ever reinstated, the
suite automatically resumes running and gating normally, and all 194
tests must pass again before this harness may report it as a live gate.

**2026-10-01 interpreter correction (BUG-047):** the harness's child
checks now use the invoking interpreter (`sys.executable`). A real run from
`backend/.venv/bin/python` passed 4/4 current checks, with CAP-007 N/A;
see `knowledge/05-QA/tools/regression-runs/RUN_20261001T071935Z.txt`.
This local correction awaits independent recovery review.

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

`.claude/security/tests/test_bash_guard.py` (194 tests) was, on its own,
a real, permanent, automated regression suite for the Bash-surface
security guard specifically — re-run clean at every checkpoint across
Phases 7-10, while CAP-007 was live. **Corrected 2026-10-01:** CAP-007
was retired 2026-09-28 (`OWN-006`/`ADR-007`); this suite is no longer a
live regression gate (it now correctly fails 149/194, testing enforcement
that was intentionally removed) and `run_regression.py` reports it
`N/A (RETIRED)` rather than a passing or failing current check. The
194-test suite itself is unmodified and preserved — see `TEST_RESULTS.md`
and `BUG-044` for the rollback instruction (all 194 must pass again before
this suite may resume being treated as a live gate, if CAP-007 is ever
reinstated).

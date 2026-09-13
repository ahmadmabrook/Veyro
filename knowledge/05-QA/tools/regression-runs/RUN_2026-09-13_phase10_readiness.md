---
doc: REGRESSION_RUN_PHASE10_READINESS
status: LIVE
date: 2026-09-13
---

# Phase 10 readiness — permanent regression harness first real run

`knowledge/05-QA/tools/run_regression.py` was authored this chunk
(SCN-MOD000-091 closure). It wraps the 5 checks this project has run by
hand after every material change since Phase 1 into one aggregate
command. Governed commit at time of this run: `7eca8b02e076dd2785abf4a846f792f28d580c2a`
(local HEAD == `origin/main`, confirmed).

**Honest disclosure:** the aggregator script itself has not been
executed end-to-end by an agent session, because it is not yet on
`.claude/security/bash_guard.py`'s trusted-script allowlist —
`.claude/security/**` is Edit/Write-denied to this session (by design,
per Phase 7's activation conditions), so adding a new trusted script
there requires an owner-authorized edit plus an independent security
re-review, matching every prior change to that file. Confirmed this
chunk: `python3 knowledge/05-QA/tools/run_regression.py` is denied
(`DISALLOWED_FLAG_OR_SHAPE`) when attempted through this session's own
governed Bash tool. It is fully runnable today by the owner or any human
terminal session outside Claude Code's guard.

What this record establishes instead: every one of the 5 checks the
harness wraps was run individually, this chunk, and all 5 passed —
the same result the harness itself would report if it could run under
this session's own tool access. This is the harness's real "first pass
record" in substance, gathered the same way its own code would gather
it, just not through the wrapper script itself.

| Check | Result | Summary |
|---|---|---|
| `verify_baselines.py` | PASS | All 4 governing baseline hashes match `PROJECT_INDEX.md` exactly |
| `validate_catalog.py` | PASS | 0 errors, 95 scenarios, 19/19 mandatory categories, 1 tracked non-blocking warning |
| `validate_capabilities.py` | PASS | 7 capabilities, all registered and APPROVED |
| `evidence_integrity_check.py` | PASS | 162 files scanned, 0 unexpected broken references |
| `test_bash_guard.py` | PASS | 194/194 tests |

**Aggregate result: PASS, 5/5 checks.**

## Follow-up (non-blocking for Phase 10, tracked honestly)

Wiring `run_regression.py` into `bash_guard.py`'s `_ALLOWED_PYTHON_SCRIPTS`
map is a real, disclosed follow-up — not attempted this chunk, since it
would require an owner-authorized edit to a `.claude/security/**` file
plus a fresh independent `veyro-security-reviewer` pass, per this
project's own established discipline for that specific file (every
prior change to `bash_guard.py` went through independent security
review before being trusted). Recommended as a Phase 10-adjacent
follow-up, not a certification blocker: the harness's constituent
checks are all real, passing, and independently runnable today; only
the convenience of running them as one wrapped command via an agent's
own governed Bash tool is deferred.

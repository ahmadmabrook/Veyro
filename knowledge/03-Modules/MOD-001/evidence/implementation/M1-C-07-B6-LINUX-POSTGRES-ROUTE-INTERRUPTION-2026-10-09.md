# M1-C-07 B6 Linux Postgres route — interrupted, not qualified

The sole guarded architecture-critical Opus implementation call `M1-C-07-LINUX-POSTGRES-ROUTE` (runner `f2ac33da-a96d-4bd7-a561-77d327af9cef`, strategy `M1-C-07-v2`) stopped at its 900-second soft no-progress budget, exit 42. Preserve its WIP: `backend/tests/harness/postgres.py`, `backend/tests/unit/test_harness_postgres_fail_closed.py`, `.github/workflows/test-pyramid.yml`, and `evidence/implementation/tools/m1c07_b6_route_check.py`. No commit, push, remote CI run, review, capability-scope expansion, or scenario promotion occurred.

Deterministic reconciliation after the stop:

- The standalone scripted-fake route check reports 56/56 PASS. It runs on macOS and does not qualify a live Linux engine.
- The approved local CAP-011 wrapper invocation of `backend-unit` reports **18 failed, 36 passed** (rc 1). The 18 new Linux-route tests fail during their fake Unix-socket setup with `OSError: AF_UNIX path too long` under the actual pytest temporary path; none is a valid Linux-route positive.
- Ruff passes for the implementation and standalone check script, but the changed unit-test file has nine `SIM117` findings. `git diff --check` for the changed tracked files passes.
- CAP-011 remains approved only for pinned local wrapper invocation; this test run is **not** code-assurance, CI, gate, or scenario evidence. CAP-012 remains unapproved. The candidate workflow is uncommitted and unrun.

Exact next bounded substep in the existing C07 operation: repair the unit-test fake socket to use a genuinely short disposable path while preserving cleanup; resolve the nine new lint findings; rerun the approved wrapper and scripted-fake negative suite. Then inspect the security boundary and only after deterministic green proceed toward code/config review, committed candidate, and real Linux positive/negative proof. B6 remains **BLOCKED**; do not designate a required status or infer SCN-MOD001-036/061/071/016 PASS.

## Same-day reconciliation after narrow repair

The follow-on guarded Sonnet call `M1-C-07-B6-UNIT-SEAM-REPAIR` (runner `cd8307c6-f59c-49ab-99ff-49a136b259b7`, strategy `M1-C-07-v3`) changed only the unit-test file. It gave the fake Unix socket a short disposable `/tmp/vq…/d.sock` path and per-test teardown, then resolved the nine new SIM117 findings. The call completed with a material test-file checkpoint. Independent local rerun of the approved wrapper: **54/54 backend-unit passed, rc 0**. Standalone scripted-fake route check: **56/56 passed**. Ruff on the changed unit-test file and `git diff --check` passed. Current unit-test SHA-256: `c8f3378147dbbcbfdc75064ee975ffc066059f82ff7a1ff7dc12239ee8840ee0`.

This closes only the local test-seam blocker above. The Linux engine route has **not** been observed on Linux, the code/config candidate remains uncommitted and unreviewed, and CAP-011 CI/required-status scope remains unapproved. B6 therefore remains blocked for CI/gate/scenario reliance. The next mandatory C07 increment is to reconcile the candidate against the B4–B6 review findings, then obtain only the planned code/config assurance and real Linux positive/negative evidence; C05 retains CAP-012/typecheck-CI and C14 retains the independent code review. No operation or scenario completion credit is taken here.

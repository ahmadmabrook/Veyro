---
capability: CAP-002 TestSprite CLI
test: positive
date: 2026-08-31
---

# CAP-002 Positive Test

Discovery: `testsprite --help`, `testsprite doctor`, `testsprite <cmd> --help` for `project`/`test`/`testlist`.

Findings:
- TestSprite CLI v0.8.0 is a thin client to a **hosted cloud service** (`https://api.testsprite.com`) — it is not a local Playwright/API/mobile driver by itself. Actual test *execution* (`test run`, `test rerun`, `testlist run`) happens server-side and is billed per run (e.g. 0.5 credits/FE rerun, 0.2/BE rerun; fresh runs billed at trigger time even if cancelled).
- `testsprite doctor` shows this machine already has an authenticated account: org "Ahmad Mabrouk's workspace", plan Starter, balance 550 credits remaining. This account pre-existed this session — MOD-000 did not create or activate it.
- Pure-local, no-network, no-credential commands exist and were used for qualification: `test scaffold` (emits a schema-correct starter plan) and `test lint` (validates a plan file offline).

Steps run (both pure-local, evidence files in this directory):
1. `testsprite test scaffold --output json` -> exit 0, produced valid frontend plan JSON (`testsprite_scaffold_output.json`).
2. `testsprite test lint --plan-from testsprite_scaffold_output.json --output json` -> exit 0, `{"checked":1,"valid":1,"issues":[]}` (`testsprite_lint_valid.json`).

Result: **PASS** for the offline plan-authoring/validation surface. Live execution surfaces (frontend browser runs, backend API runs, mobile) are NOT qualified here — see `negative_test.md` and `SCOPE_NOTE.md` for why, and what remains BLOCKED pending owner decision on credit spend.

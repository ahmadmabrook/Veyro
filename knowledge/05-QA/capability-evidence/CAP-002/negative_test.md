---
capability: CAP-002 TestSprite CLI
test: negative
date: 2026-08-31
---

# CAP-002 Negative Test

Steps: wrote a deliberately malformed plan file (`bad_plan.json`, missing every required field) and ran `testsprite test lint --plan-from bad_plan.json --output json`.

Result: **PASS**. Exit code 5 (validation error, per the CLI's documented exit-code contract), structured JSON listing all 4 problems (missing `projectId`, invalid `type`, missing `name`, missing `planSteps`), no network call made, no partial/silent acceptance. Fail-closed behavior confirmed for the offline surface.

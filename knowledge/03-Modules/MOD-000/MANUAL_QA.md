---
doc: MOD-000_MANUAL_QA
status: LIVE
updated: 2026-09-05
---

# MOD-000 — Manual QA (index)

Appendix D field: "Every Required scenario manual execution record/evidence."

Real fresh-context, Opus-tier (`veyro-manual-qa`) execution record:
`knowledge/03-Modules/MOD-000/evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md`
(supersedes the grading in the original `CAPABILITY_DRILL.md`, which is
retained, not deleted, per the project's standing "preserve history" rule).

| Surface | Result | Note |
|---|---|---|
| Browser | PASS | Real multi-field form fill + submit, server-echoed |
| Backend/API | PASS | Write independently confirmed by a separate subsequent read (proxy for real backend state — none exists before MOD-001) |
| iOS Simulator | PASS | Full interactive lifecycle incl. negative deep-link control, PID-verified background/foreground |
| Android | BLOCKED | SDK/adb/emulator installed, but no AVD/system-image provisioned (owner-approval-scale action) |
| Accessibility | BLOCKED — OWNER_ASSISTED REQUIRED | Re-tested: preference write does not activate the real screen-reader process |
| Edge/device | BLOCKED — NOT YET QUALIFIED | No Edge/BrowserStack/Sauce tooling available |

No scenario has ever been marked PASS from code inspection, TestSprite,
or automated output alone — every PASS above has real interactive
evidence (screenshots, request/response, PID comparisons) in the linked
file.

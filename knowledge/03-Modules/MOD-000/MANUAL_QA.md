---
doc: MOD-000_MANUAL_QA
status: LIVE
updated: 2026-09-12 (Phase 9 restoration proof re-review, Gatekeeper P2-3 — Android/Edge-device rows corrected to OWNER_ASSISTED per chunk 27's canonical disposition model, reinstated distinct from BLOCKED)
---

# MOD-000 — Manual QA (index)

Appendix D field: "Every Required scenario manual execution record/evidence."

Real fresh-context, Opus-tier (`veyro-manual-qa`) execution record, current:
`knowledge/03-Modules/MOD-000/evidence/manual-qa/CAPABILITY_DRILL_PHASE6_2026-09-05.md`
(Phase 6, technically model-attested via `mr_verify.py`, not self-report).
Supersedes the grading in `CAPABILITY_DRILL_PHASE5_RERUN.md` and the
original `CAPABILITY_DRILL.md`, both retained, not deleted, per the
project's standing "preserve history" rule.

| Surface | Result | Note |
|---|---|---|
| Browser | PASS | Real multi-field form fill + submit, server-echoed, 2 negative controls |
| Backend/API | PASS | Independently-verified stateful side effect (set/read/delete cookies, separate re-read confirms selective survival) + 5 negative paths; proxy for real backend state — none exists before MOD-001 |
| iOS Simulator | PASS | Full interactive lifecycle incl. a genuine cold-launch cycle (new PID, cleared state) and negative deep-link/launch controls, PID-verified background/foreground |
| Android | OWNER_ASSISTED | `adb`/`emulator` binaries present but no AVD/system-image provisioned — an owner-approval-scale provisioning action, not a tooling gap; fail-closed proof added (invalid AVD name fails loudly). Reinstated as OWNER_ASSISTED, distinct from BLOCKED, in Phase 8 chunk 27 per explicit owner instruction that the two carry different governance meaning |
| Accessibility | OWNER_ASSISTED | Corrected 2026-09-05 (BUG-011): the screen reader *can* be started for real (`launchctl`/`kickstart`, real PID, moving focus cursor, real speech audio) — but announcement text still cannot be captured and its own gestures still cannot be driven, requiring a human. Reinstated as OWNER_ASSISTED in Phase 8 chunk 27 |
| Edge/device | OWNER_ASSISTED | No Edge/BrowserStack/Sauce tooling available — every real option is a paid service, and spend decisions are owner-reserved per DC-16. Reinstated as OWNER_ASSISTED in Phase 8 chunk 27 |

No scenario has ever been marked PASS from code inspection, TestSprite,
or automated output alone — every PASS above has real interactive
evidence (screenshots, request/response, PID comparisons) in the linked
file.

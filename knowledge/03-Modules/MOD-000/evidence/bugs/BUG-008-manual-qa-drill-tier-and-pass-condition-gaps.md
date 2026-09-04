---
doc: BUG-008
status: FIXED (2026-09-04, same chunk) — F5-002/006/007/025 all remediated with real evidence; see final update at bottom
found_date: 2026-09-04
found_by: Phase 5 independent review (F5-002, F5-005 [manual-QA portion], F5-006, F5-007, F5-025)
severity: P1
---

# BUG-008: §12.1 Manual QA drill — wrong tier, unregistered capabilities, pass-conditions not met

## What is wrong (consolidated — five related findings, one root drill)

1. **F5-002**: the drill's evidence was produced using
   `mcp__Claude_Browser__*` and `mcp__Claude_Code_iOS_Simulator__*` tools —
   neither is in `CAPABILITY_REGISTRY.md` or `module-capabilities.yaml`.
   Used for real mandatory-gate work, not a qualification drill.
2. **F5-006**: the drill was run by the implementing main session using ad
   hoc tool calls, not a formal fresh-context invocation of the named
   `veyro-manual-qa` agent (Opus). No MR evidence exists for it.
3. **F5-007**: measured against the EIP's own §12.1 pass conditions,
   3 of the 6 "PASS" surfaces don't actually qualify — Browser (no
   input/submit, static public page), Backend/API (one read-only GET
   against a public echo service, no side effects observed), iOS (boot +
   one screenshot only, no interactive tap/deep-link/background-foreground
   — and this directly contradicts SCN-061, which correctly records the
   same interactive-control gap as BLOCKED).
4. **F5-025**: BUG-005 (2026-09-01) fixed the Accessibility/Edge overclaim
   but never applied the same scrutiny to the sibling surfaces in the same
   drill, so the same overclaim class survived in 3 more rows.

## Governing requirement

EIP §12.1 surface table + "Qualification pass condition" column (Browser:
input+submit; Backend/API: side effects observed, response-only
insufficient; iOS: launch+interact+deep-link+background/foreground).
§4.1: manual QA routes to Opus, fresh context. `CAPABILITY_POLICY.md`
line 25: unregistered capability use against real work is
`BLOCKED: CAPABILITY_UNREGISTERED`.

## Remediation applied and verified (2026-09-04)

A fresh-context `veyro-manual-qa` (Opus) invocation redid the drill for
real. Result: `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md`.

- **F5-006 (tier)**: satisfied — this run genuinely was `veyro-manual-qa`,
  fresh context, Opus.
- **F5-007 (pass conditions)**: satisfied for the 3 surfaces that can be
  satisfied at all right now — Browser (real form fill + submit, 5 control
  types, server echo confirmed), Backend/API (a write independently
  confirmed by a *separate* subsequent read — set/delete cookie keys,
  verified via a second `GET`, not just an echo of the same request; the
  file explicitly names this as a proxy for "authoritative backend state,"
  since no real Veyro backend exists before MOD-001), iOS (full lifecycle:
  tap, swipe with observed scroll, two-finger pinch, text entry, two deep
  links, a negative-control invalid deep link that correctly failed
  differently from the valid one, HOME background/foreground verified by
  identical process PID before and after).
- **F5-025 (affected-family regression)**: satisfied — Accessibility was
  actually re-tested this run (wrote the VoiceOver-enabled preference,
  confirmed via readback, confirmed it did NOT actually activate the
  screen reader process, reverted), not just re-asserted from BUG-005's
  original text.
- **F5-002 (unregistered capabilities)**: satisfied — CAP-005 (Browser,
  QUALIFIED — positive test only, no negative test yet, correctly not
  marked APPROVED) and CAP-006 (iOS Simulator, APPROVED — positive + a
  genuine negative control) both registered in `CAPABILITY_REGISTRY.md`,
  qualified by this same Opus-tier run.

Two real, still-open findings surfaced as a byproduct, not part of this
bug: `computer:type` silently fails on `<input type="time">` fields (a
harness tool defect, worth carrying into any future browser-automation
work), and `read_page`'s accessibility-tree output does not report
`<textarea>` values.

**Remaining, correctly still BLOCKED (not this bug's defect — genuine
infrastructure gaps):** Android (SDK/tools exist, but no AVD/system image
provisioned — provisioning one is an owner-approval-scale action, not done
unilaterally), Accessibility (real screen-reader execution), Edge/device
(no Edge/BrowserStack/Sauce tooling installed). SCN-MOD000-061 (iOS
interactive control) can now be closed as PASS.

## Affected

SCN-039, SCN-040, SCN-041, SCN-042, SCN-043, SCN-044, SCN-061, SCN-032,
BUG-005. **Blocks MOD-000 certification: YES** until all 6 surfaces
genuinely meet their §12.1 pass conditions with fresh-context Opus
evidence.

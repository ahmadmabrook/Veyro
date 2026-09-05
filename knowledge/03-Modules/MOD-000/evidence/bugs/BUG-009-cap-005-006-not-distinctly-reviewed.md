---
doc: BUG-009
status: OPEN (2026-09-05)
found_date: 2026-09-05
found_by: Second fresh-context Phase 5 re-review (veyro-code-reviewer, Opus, N-6/F5-002)
severity: P2
---

# BUG-009: CAP-005/CAP-006 qualified and "approved" by the same invocation, never independently reviewed

## What is wrong

`CAPABILITY_REGISTRY.md` lists CAP-005 (Browser tools) and CAP-006 (iOS
Simulator control) as `QUALIFIED`, both qualified by `veyro-manual-qa`
(fresh context, Opus) on 2026-09-04. This registry entry itself already
carried an honest note: "the qualifying agent and the 'independent'
reviewer would currently be the same invocation, which doesn't satisfy
reviewer/implementer separation." Despite that honest note, two durable
documents (`CR-MOD000-001.md`'s F5-002 row, `CURRENT_STATE.md`'s manual-QA
checklist line) incorrectly stated CAP-006 as `APPROVED` — a real
misreport, not just an unresolved gap. The second Phase 5 re-review
caught this (finding N-6, tied to F5-002).

## Why this matters

`CAPABILITY_POLICY.md` states only `APPROVED` capabilities may be used
for real project work — but CAP-005/CAP-006 already produced the mandatory
EIP §12.1 Browser/iOS manual-QA gate evidence (`CAPABILITY_DRILL_PHASE5_RERUN.md`,
closing SCN-MOD000-061) while sitting at `QUALIFIED`, not `APPROVED`. This
is the exact same qualifying-agent-is-the-reviewing-agent gap CAP-001/
CAP-002 had before BUG-006's remediation — the fix pattern is already
established and known to work.

## Remediation applied (2026-09-05)

1. Fixed the two misreports (`CR-MOD000-001.md` F5-002 row,
   `CURRENT_STATE.md`) to correctly say QUALIFIED, not APPROVED.
2. Filed this bug rather than leaving the gap as an unlinked registry
   footnote.
3. Spawned a distinct fresh-context Opus review (`veyro-security-reviewer`,
   not `veyro-manual-qa`) to independently evaluate CAP-005/CAP-006's
   existing qualification evidence and make the APPROVED/QUALIFIED/
   REJECTED call, mirroring the exact operating model BUG-006 established
   for CAP-001/CAP-002 — see this file's own update below once that
   review lands.

## Affected

`CAPABILITY_REGISTRY.md` (CAP-005/CAP-006 rows), `CAPABILITY_POLICY.md`
(usability gate), SCN-MOD000-061 (the scenario whose evidence rests on
these capabilities). Does not block MOD-000 certification on its own —
CAP-005/CAP-006 are control-plane tooling used to gather manual-QA
evidence, not a product capability — but the mismatch between "used for
mandatory gate evidence" and "not independently approved" should be
closed before Phase 10, not carried indefinitely.

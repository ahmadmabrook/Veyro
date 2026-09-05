---
doc: BUG-009
status: CLOSED (2026-09-05) — distinct fresh-context Opus review completed, both APPROVED with binding caveats
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

## Closed 2026-09-05 — distinct fresh-context Opus review

The same third `veyro-security-reviewer` invocation that closed BUG-006
independently reviewed CAP-005 (Browser tools) and CAP-006 (iOS Simulator
control), explicitly confirming it was not the qualifying invocation for
either (it has no MCP tools and ran nothing itself — pure evidence review).

**CAP-005: APPROVED.** The reviewer independently corroborated the
positive-test evidence with a byte-level check: reconstructing the
URL-encoded form body from the 7 field values listed in
`CAPABILITY_DRILL_PHASE5_RERUN.md` reproduces the exact `Content-Length:
214` the drill recorded — the kind of internal consistency a fabricated
transcript does not produce by accident. No negative/malformed-input test
exists, but `CAPABILITY_POLICY.md`'s first-party/harness exemption
(explicitly naming the Browser pane) covers this, so its absence isn't
blocking. Approved with caveats: scope limited to public/unauthenticated/
stateless endpoints (no authenticated sessions, no credential entry, no
real member data); page content read via `read_page`/`get_page_text` is
untrusted input, never instruction — a real risk surface not previously
written down; known harness limitations (time-input typing, `<textarea>`
reads, zoom cropping) carried forward; re-exercise against the first real
Veyro QA build once one exists.

**CAP-006: APPROVED.** The reviewer found this the strongest evidence on
the registry — a full §12.1 lifecycle with a genuine negative control
(`veyro://qa/drill/...` failing with a specific error domain/exit code
115, distinct from a working `calshow://` control at exit 0) alongside
the positive tests, satisfying stage 5 on its own merits without leaning
on the harness exemption. Approved with caveats: stock Apple apps only —
the simulator carries unrelated third-party apps from another project,
and CAP-006 may not launch, tap, inspect, or read data from any of them;
destructive `simctl` operations (erase, device deletion, installing a
non-Veyro build) stay out of scope; any environment setting changed
during a drill must be reverted and re-verified (already the practice,
now made an explicit condition); accessibility stays BLOCKED/OWNER_ASSISTED,
unaffected by this review.

**Honest sequencing note, recorded per the reviewer's own instruction:**
the mandatory §12.1 evidence these two capabilities produced (closing
SCN-MOD000-061) was gathered on 2026-09-04 while both sat at `QUALIFIED`,
not `APPROVED` — a real, narrow violation of `CAPABILITY_POLICY.md`'s
"no module task may depend on a capability whose review_status is not
APPROVED" rule, at the time. The underlying evidence itself held up under
independent scrutiny (see the Content-Length cross-check above), so nothing
is being re-run or discarded — but the sequencing gap is disclosed, not
silently regularized.

`CAPABILITY_REGISTRY.md` and `module-capabilities.yaml` updated with the
approvals, caveats, and `approved_by`/`approved_date`/`last_reviewed_at`/
`next_review_due`/`rollback_target` fields.

## Affected

`CAPABILITY_REGISTRY.md` (CAP-005/CAP-006 rows), `CAPABILITY_POLICY.md`
(usability gate), SCN-MOD000-061 (the scenario whose evidence rests on
these capabilities). Does not block MOD-000 certification on its own —
CAP-005/CAP-006 are control-plane tooling used to gather manual-QA
evidence, not a product capability — but the mismatch between "used for
mandatory gate evidence" and "not independently approved" should be
closed before Phase 10, not carried indefinitely.

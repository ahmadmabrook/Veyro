---
doc: BUG-016
status: FIXED (2026-09-06); corrected 2026-09-06 (Phase 7 re-review, RR-6/RR-7); item now genuinely routed to owner (non-blocking)
found_date: 2026-09-06
found_by: Phase 7 fresh-context Opus veyro-security-reviewer (SEC-10); corrected by a second fresh-context re-review
severity: P2
---

# BUG-016: The personal-data classification audit overclaimed "repo-wide" scope

## What is wrong

`DATA_CLASSIFICATION_AUDIT.md`'s own Method section says "Repo-wide
pattern scans," but every listed command targets `knowledge/` only.
`veyro-product-experience-design/` (2.9 MB, 54 files, the frozen
VEYRO-UX-V1-170-APPROVED design-bundle baseline) was never scanned.
`CURRENT_STATE.md` separately repeated the same "repo-wide"
characterization.

## Real findings from the actually-repo-wide re-scan (2026-09-06)

12 email-shaped strings and 6 distinct Jordanian-format phone numbers,
design-mockup demo data inside a frozen baseline this project cannot
modify (`Edit`/`Write` denied against `veyro-product-experience-design/**`)
and does not process. One email (`sara.halabi@gmail.com`) sits on a
real-domain provider rather than a reserved-by-construction one, unlike
the two `knowledge/`-scoped emails the original audit found.

**Correction (2026-09-06, Phase 7 re-review, RR-6):** this bug file and
`DATA_CLASSIFICATION_AUDIT.md`'s correction section both originally
stated all matches were "inside `project/veyro-screen.js`." A second,
independent fresh-context re-review found and this session confirmed by
direct re-scan that this is wrong: only 6 of the 12 emails and 1 of the 6
phone numbers are in `veyro-screen.js` — the rest are spread across at
least 12 distinct `.dc.html` design-artboard files (`Veyro V1 Batch G
Member Record and Lifecycle.dc.html`, `Batch J Staff and Communication`,
`Batch L Settings Search and Auth`, `Batch Q Console`, `Batch F Command
and CRM`, `Batch M Front Desk and POS`, `Batch O Member Training and
Nutrition`, `DS Validation Screens`, `HF CRM and Console`, `HF Member 360`
and `HF Member 360 AR`, `Wireframes`). The demo PII spans the design
bundle broadly, not one file. Risk posture is unaffected either way
(the whole directory is frozen and Edit/Write-denied), but a correction
authored specifically to fix a scope overclaim should not itself
misstate scope.

## Remediation applied (2026-09-06)

`DATA_CLASSIFICATION_AUDIT.md` corrected: original text preserved
unedited, a dated correction section appended documenting the actual
scan scope, the design-bundle findings, and an explicit statement of what
this audit does and does not establish (it does not determine whether
any of the 12 addresses/6 numbers correspond to a real, reachable
mailbox or line — that cannot be determined from repo content alone).
`CURRENT_STATE.md`'s "repo-wide" claim corrected to match.

## Open item routed to the owner (non-blocking)

Whether any of this design-mockup content is real personal data, and
whether its presence in a frozen, approved design baseline requires any
action beyond the current read-only, no-processing status quo, is not
something this project can determine or decide unilaterally.

**Correction (2026-09-06, Phase 7 re-review, RR-6):** the original
version of this section claimed this had already been "recorded as an
open item" in `OWNER_APPROVALS.md`. It had not — a real gap, found by a
second independent re-review, not self-caught. Fixed now: see
`OWNER_APPROVALS.md`'s pending-decisions list (will get an `OWN-004` row
once decided).

## Certification impact

Does not block Phase 7. The scope-overclaim itself is fixed; the "is any
of this real" question is a disclosed, non-blocking open item (the
finding is about the audit's own documentation accuracy, not about a
security control that failed).

## Affected

`knowledge/03-Modules/MOD-000/evidence/security/
DATA_CLASSIFICATION_AUDIT.md`, `knowledge/00-System/CURRENT_STATE.md`,
SCN-MOD000-074(b).

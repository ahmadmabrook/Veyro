---
doc: BUG-046
status: CLOSED
---

# BUG-046 — `BUG_REGISTRY.md`'s own BUG-037 row said OPEN while its own row text, its own file, `ADR-008`, `STATUS.md`, and `CURRENT_STATE.md` all already said CLOSED

**Module:** MOD-000 (documentation: `knowledge/05-QA/BUG_REGISTRY.md`)
**Severity:** P2 (documentation-consistency, non-blocking, no false-clean
risk — every external source of truth was already correct; only this
file's own status cell and one orphaned narrative paragraph had drifted)
**Status:** CLOSED (2026-10-01), same session as filing, Sonnet-tier
recovery remediation.

## Summary

`BUG-037` (`mr_verify.py` rejecting the current Opus model id) was filed
2026-09-29 and closed the same day after 2 remediation rounds + 3
independent review passes. Its own canonical file,
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-037-mr-verify-rejects-current-opus-model-id.md`,
has carried `status: CLOSED (2026-09-29...)` in its front matter since
that day. `knowledge/04-Decisions/ADR-008-dc17-requalification-opus-5-5-sonnet-5.md`
records the DC-17 re-qualification that was part of the same closure.
`knowledge/03-Modules/MOD-001/STATUS.md` (line 639) and
`knowledge/00-System/CURRENT_STATE.md` (line 16) both correctly say
CLOSED.

`BUG_REGISTRY.md`'s own table row for `BUG-037`, despite its own
narrative cell describing the full 2-round-plus-3-review closure in
detail, still had its status field reading **`OPEN (2026-09-29)`** —
self-contradicted by its own row text, and contradicted by every
external source above. Independently verified by direct read of all
five sources before treating this as real (not taken on the recovery
brief's word).

Separately, a narrative paragraph earlier in the same file (the
`BUG-037`-filing entry, added 2026-09-29) explicitly declared itself
"the current, latest state of this table: ... 1 open P1 (`BUG-037`...).
2 open P2 (`BUG-010`, `BUG-033`...)". This file's established convention
is a chronological chain of such dated paragraphs, each legitimately
true until the next one supersedes it — not itself a defect. But no
later paragraph ever arrived to supersede this one specifically:
`BUG-037`'s closure and `BUG-038` through `BUG-045` were all recorded
only as table rows and front-matter `updated:` entries from that point
forward, leaving this one paragraph's "current, latest state" claim
orphaned.

## Fix

Both corrected with dated annotations, original text preserved
(struck through where directly superseded, not deleted):

1. `BUG-037`'s table row: status cell changed from `**OPEN (2026-09-29)**`
   to `**CLOSED (2026-09-29), 2 remediation rounds + 3 independent review
   passes**`, citing this bug.
2. The orphaned "current, latest state" paragraph: the stale totals
   sentence struck through, a correction appended explaining both that
   `BUG-037` closed the same day and that the file's own chronological-chain
   convention is sound — the gap was this one entry never being
   superseded, not the convention itself being wrong — and pointing to
   the front-matter `updated:` line as the current authoritative source.

## Verification

Independently re-derived real current totals by extracting every table
row's status cell directly (not trusting any prior claim, including this
session's own prior-batch notes): exactly 7 rows currently read OPEN —
`BUG-010` (P2), `BUG-033` (P2), `BUG-037` (now fixed to CLOSED by this
bug), `BUG-038` (P1), `BUG-039` (P3), `BUG-040` (P2), `BUG-041` (P3).
After this fix: **0 open Blocker/P0. 1 open P1 (`BUG-038`). 3 open P2
(`BUG-010`, `BUG-033`, `BUG-040`). 2 open P3 (`BUG-039`, `BUG-041`).**
This matches the totals this session's own prior-batch front-matter
entries (`BUG-042` through `BUG-045`) had already been stating — those
were correct; only `BUG-037`'s own row and the one orphaned paragraph
had not caught up.

Also re-run clean this batch: `evidence_integrity_check.py` (exit 0,
320 files, 0 broken refs) + its tests (6/6), `capability_drift_check.py`
(exit 0, 8/8, 0 errors) + its tests (21/21), `run_regression.py` (exit 0,
aggregate PASS 4/4, 1 N/A) + its tests (9/9), `verify_baselines.py` (4/4
PASS), `validate_capabilities.py` (7/7 PASS), capability manifests for
MOD-000 (7/7) and MOD-001 (9/9) both PASS. `git rev-parse HEAD` ==
`origin/main`, unchanged — uncommitted working-tree edit only.

## Scope note

Does not touch `BUG-038`'s own status (still `OPEN`), does not qualify
CAP-008, does not address `BUG-010`/`BUG-033`/`BUG-040` (unrelated,
unchanged, still correctly `OPEN`).

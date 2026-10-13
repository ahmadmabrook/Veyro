---
doc: BUG-043
status: CLOSED — 2026-10-01 independent Opus recovery assurance
---

# BUG-043 — `capability_drift_check.py` misparsed its own snapshot table and ignored capability lifecycle state

**Module:** MOD-000 (tool: `knowledge/05-QA/tools/capability_drift_check.py`)
**Severity:** P1 (false-FAIL on a governance gate, including a semantically
wrong "requires reapproval before continued reliance" finding against a
capability that is no longer relied upon — misleading enough to block or
mislead a real recovery/qualification decision, not merely cosmetic)
**Status:** CLOSED — 2026-10-01 independent Opus recovery assurance. Fixed
2026-10-01, same session as filing, Sonnet-tier recovery remediation.
**Corrected 2026-10-01 (independent Opus recovery review, session
`veyro-recovery-opus-gate-20261001`, model `claude-opus-5-5`): this file
originally said CLOSED — overclaimed. The fix itself was technically
re-verified by that review (part of a 38/38 pass across BUG-043/044/045's
combined test suites, plus validators), but the review's overall verdict
was BLOCKED specifically because this file's and `BUG_REGISTRY.md`'s
CLOSED language was itself a premature-completion finding — a Sonnet-tier
local fix is not a closure until a fresh independent assurance pass
approves it as such. That BLOCKED finding was superseded by the same independent Opus session's targeted re-review at 2026-10-01 11:33:47 UTC: APPROVED, P0=0/P1=0. This is recovery assurance only, not CAP-008 qualification or an R04 gate. **Batch 7 attribution correction (2026-10-01):** The later claim that this reviewer re-confirmed BLOCKED on a totals inconsistency was erroneous; the saved ACPX history records APPROVED at 11:33:47 UTC. Earlier BLOCKED text above remains as historical sequence. Model attestation:
reviewer's model attestation PASSED `mr_verify.py` (genuine Opus
transcript, 51 turns); grounded in `DC-06` ("no self-approval" — a
reviewer/Gatekeeper runs in a fresh context separate from the
implementing session) — the Sonnet session that fixed this bug cannot
be the one that closes it. See
`knowledge/05-QA/BUG_REGISTRY.md`'s front matter for the corrected
aggregate totals this finding also required.

## Summary

Independent recovery-gate review found the authoritative run of
`capability_drift_check.py` exiting 1 with 12 findings, none of them a
real, currently-actionable material-change. Three distinct defects, all in
how the script read `CAPABILITY_REGISTRY.md`:

1. **Snapshot table misparsed as live rows.** `parse_registry_rows`
   scanned the *entire* file for lines starting `| CAP-`, including the
   "## Version/hash snapshot at approval" section's own 3-cell rows (e.g.
   `| CAP-001 | live server, tools observed 2026-08-31 | N/A (hosted) |`).
   Those don't match `REGISTRY_COLUMNS`' 15 cells, so all 8 were reported
   as `UNPARSEABLE REGISTRY ROW` — 8 of the 12 findings were this alone.
2. **Retirement treated as unreviewed drift.** CAP-007's content changed
   (BUG-036 Tier 1, 2026-09-26) after its snapshot was taken, then it was
   retired entirely (`OWN-006`/`ADR-007`, commit `058ed27`, 2026-09-28).
   The script still ran the mismatch through its "MATERIAL CHANGE
   DETECTED... requires a fresh stage 4-5 pass before continued reliance"
   path — nonsensical for a capability nothing is continuing to rely on.
3. **Pending capability compared as though approved.** CAP-008 has never
   been approved (`review_status: PENDING`, `BUG-038` open). Its snapshot
   row (recorded at registration) differs from its current live values
   (Docker/image metadata refreshed since). The script flagged this the
   same way as an approved capability's post-approval drift, which
   `BUG-025`/`SCN-MOD000-084`'s own framing never intended — that gate is
   about an *approved* capability silently changing, not pre-approval
   churn on something still `PENDING`.

## Fix

`knowledge/05-QA/tools/capability_drift_check.py`:

- `parse_registry_rows` now only scans the live table (text before the
  `## Version/hash snapshot at approval` marker — the same marker
  `parse_snapshot` already split on, now shared as `SNAPSHOT_MARKER` so
  the two parsers can't disagree on the boundary).
- New `parse_retired_capabilities()` reads this file's own existing
  dated-prose convention (`**CAP-NNN status update (DATE): RETIRED.**`,
  introduced for CAP-007's 2026-09-28 retirement) rather than inventing a
  new structure.
- New `is_approved()` checks a row's `review_status` cell actually starts
  with `APPROVED` (bold-marker-stripped) before treating it as having an
  approval baseline to drift-check against.
- Per-capability decision logic extracted into `evaluate_capability()`
  (pure function, both used by `main()` and directly unit-tested):
  retired/revoked → INFO only, explicitly named non-live, reapproval gate
  not applicable (drift not silently hidden — still reported, just not as
  an error); not-yet-approved → INFO only, explicit "no approval baseline
  to drift-check against"; approved and live → unchanged strict behavior
  (missing snapshot = error, mismatch = `MATERIAL CHANGE DETECTED` error,
  match = clean INFO).

No blanket exemption was added anywhere — every one of the 8 capabilities
is still individually evaluated and named in the output; the fix changes
*which* bucket each falls into, not whether it's checked.

## Verification

`capability_drift_check.py` — before: exit 1, 12 errors (8 misparsed rows,
2 CAP-007 false material-change, 2 CAP-008 false material-change). After:
exit 0, 8/8 capabilities checked, 0 errors, 8 INFO lines (6 "no drift" +
1 "RETIRED — non-live" + 1 "not yet approved").

New `knowledge/05-QA/tools/test_capability_drift_check.py` — 12/12 pass:
snapshot rows not misparsed (positive, the core defect); malformed live
row still fails closed (negative/regression-guard); retired capability
with real drift → INFO not error, and with no drift → still INFO
(2 cases); pending capability with drift and with no snapshot → both INFO
not error (2 cases); `is_approved()` rejects PENDING / accepts APPROVED
variants; **approved capability with drift still errors, missing snapshot
for an approved capability still errors, approved+no-drift stays clean
INFO** (3 cases proving fail-closed behavior is unchanged for the actual
target case BUG-025 was written for).

Also re-run clean after this fix: `evidence_integrity_check.py` (exit 0,
317 files, 0 broken refs), its own test suite (6/6), `verify_baselines.py`
(4/4 PASS), `validate_capabilities.py` (7/7 PASS), capability manifests
for MOD-000 (7/7) and MOD-001 (9/9) both PASS. `git rev-parse HEAD` ==
`origin/main`, unchanged — uncommitted working-tree edit only.

## Scope note

CAP-008 remains `PENDING`; `BUG-038` remains `OPEN`; this fix does not
qualify, approve, or otherwise change CAP-008's status — it only corrects
how an unrelated tooling script was *comparing* CAP-008's values. Same for
CAP-007: still `RETIRED`, this fix doesn't reactivate or re-approve it.

## Final independent closure — 2026-10-01

Fresh independent `claude-opus-5-5` review session `veyro-recovery-opus-gate-20261001` returned **APPROVED**, P0=0/P1=0, after its initial BLOCKED verdict and the records-only remediation. Runtime model attested by `mr_verify.py`; 38/38 focused tests and validators passed in the review copy. This closes this recovery defect, not CAP-008 or BUG-038. Earlier pending/blocked statements above are historical and superseded by this final verdict.

## Final independent closure correction — 2026-10-01

The independent fresh-context Opus session `veyro-recovery-opus-gate-20261001` gave a targeted final verdict **APPROVED, P0=0/P1=0** at 11:33:47 UTC after reviewing the corrected status records. `mr_verify.py` attested `claude-opus-5-5`; 38/38 focused tests and validators passed in its earlier technical pass. The subsequent Batch 7 phrase “re-confirmed BLOCKED” misattributed a verdict that never occurred; the later `veyro-recovery-opus-after-b6-20261001` review identified that records error. Current status is CLOSED on this independent approval, not Sonnet self-approval. CAP-008 and BUG-038 remain separate and unapproved.

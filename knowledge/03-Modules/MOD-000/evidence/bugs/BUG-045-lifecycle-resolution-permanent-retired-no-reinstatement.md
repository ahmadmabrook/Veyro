---
doc: BUG-045
status: CLOSED — 2026-10-01 independent Opus recovery assurance
---

# BUG-045 — shared CAP-007 lifecycle parser let any RETIRED marker win permanently, with no reinstatement path and no authorization check

**Module:** MOD-000 (tool: `knowledge/05-QA/tools/capability_drift_check.py`,
consumed by `knowledge/05-QA/tools/run_regression.py`)
**Severity:** P1 (two governance gates — material-change drift detection
and the permanent regression harness — both derive "is this capability
currently retired" from a parser that could be permanently wrong in
either direction: stuck RETIRED forever, or silently retirable by an
unauthorized edit)
**Status:** CLOSED — 2026-10-01 independent Opus recovery assurance. Fixed
2026-10-01, same session as filing, Sonnet-tier recovery remediation,
following on from `BUG-043`/`BUG-044`. (This line originally said
CLOSED — overclaimed; harmonized 2026-10-01 with the "scheduled recovery
correction" section below, both reflecting the same independent Opus
recovery review's P1 finding — session `veyro-recovery-opus-gate-20261001`,
model `claude-opus-5-5`, reviewer's `mr_verify.py` attestation PASSED
(genuine Opus transcript, 51 turns), grounded in `DC-06` ("no
self-approval"). See `knowledge/05-QA/BUG_REGISTRY.md`'s front matter
for the corrected aggregate totals this finding also required.)

## Summary

`BUG-043` (capability_drift_check.py) and `BUG-044` (run_regression.py)
both introduced reliance on a single function, `parse_retired_capabilities()`,
that matched `**CAP-NNN status update (DATE): RETIRED.**` prose markers
anywhere in `CAPABILITY_REGISTRY.md` and returned the match as fact, with
three real flaws found before closing this recovery:

1. **No reinstatement path.** `finditer` + dict-comprehension kept
   whichever match came *last in document order*, not latest by date. If
   a capability were ever reinstated (a later `**CAP-NNN status update
   (LATER-DATE): REINSTATED.**` or `...ACTIVE.**` marker added below the
   original), the original RETIRED marker — appearing earlier in the
   file — would still be found by `finditer`, and because the dict
   comprehension iterates in match order, the *later* (correct) entry
   would actually overwrite it in the dict... but only by document-order
   coincidence, not by date comparison. A marker added *above* the
   retirement note (easy to do by accident, e.g. inserting into the
   "Lifecycle status" section instead of appending after the existing
   note) would have been silently ignored.
2. **No authorization/corroboration check.** Any text anywhere in the
   file matching the marker's exact shape was trusted outright. An
   accidental or unauthorized `**CAP-001 status update (DATE): RETIRED.**`
   sentence — e.g. pasted into the wrong section, or a typo'd capability
   ID — would silently suppress that capability's real material-change
   drift-gating in `capability_drift_check.py` and silently exclude its
   suite from `run_regression.py`'s aggregate, with no cross-check
   against the registry's own structured `lifecycle_status` record.
3. **No same-date conflict detection.** Two markers for the same
   capability on the same date with different status words (a malformed/
   duplicate edit) would resolve to whichever `finditer` happened to
   visit second, silently — not flagged as the data-integrity problem it
   is.

## Fix

Replaced `parse_retired_capabilities()` with
`resolve_capability_lifecycle(text) -> (resolved, conflicts)` in
`capability_drift_check.py`:

- `STATUS_UPDATE_RE` now captures the date as a literal `\d{4}-\d{2}-\d{2}`
  group (not free text) and recognizes all 4 status words
  (`RETIRED`/`REVOKED`/`REINSTATED`/`ACTIVE`), collapsed via
  `_lifecycle_bucket()` into `RETIRED` or `ACTIVE`.
- All markers per capability are collected, grouped by date; a genuine
  same-date disagreement is a **conflict**, resolved to nothing (fails
  closed). Otherwise the **latest date wins**, by actual date comparison
  — a later REINSTATED/ACTIVE marker now correctly supersedes an earlier
  RETIRED one regardless of document position.
- The winning marker must be corroborated by a matching
  `CAP-NNN's \`lifecycle_status\` is now **\`WORD\`**` sentence in the
  same bucket (the existing "## Lifecycle status" section's own
  phrasing, already present for CAP-007 from the prior batch). No
  corroborating sentence, or a disagreeing one, is a **conflict** —
  resolved to nothing, never silently trusted as either RETIRED or
  ACTIVE.
- Conflicts are returned explicitly, never silently dropped.
  `capability_drift_check.py`'s `main()` adds them directly to `errors`
  (fail closed — a registry-integrity problem is itself a FAIL).
  `run_regression.py`'s `retired_capability_ids()` takes an optional
  `conflicts_out` list, prints any conflicts prominently, and — critically
  — never includes an unresolved capability in the returned retired-set,
  so `test_bash_guard.py` keeps running/gating normally rather than being
  silently excluded on an untrustworthy claim.

`run_regression.py` updated to call `cdc.resolve_capability_lifecycle`
via the new `retired_capability_ids(conflicts_out=...)` instead of the
removed function; `main()` prints any conflicts before the results table.

## Verification

New tests added to `test_capability_drift_check.py` (now 21 tests,
up from 12): later REINSTATED marker wins over an earlier RETIRED one
and the reinstated capability's real drift is gated normally again
(2 tests); unauthorized/unbacked RETIRED marker does not suppress drift,
still errors on real drift (1 test); marker disagreeing with the field
sentence also fails closed (1 test); same-date conflicting markers fail
closed (1 test); an identical same-date duplicate is explicitly NOT a
conflict (1 test, precision check); the real registry's current CAP-007
state resolves cleanly with zero conflicts (1 test); a capability with no
marker at all is simply absent, unaffected (1 test); the superseded
single-marker test updated to require corroboration (1 test, was
previously trivially true).

New tests added to `test_run_regression.py` (now 9, up from 6):
`retired_capability_ids` reports zero conflicts against the real
registry; only the RETIRED bucket is ever returned, never an
ACTIVE/reinstated id (monkeypatched fake registry); an unauthorized
marker does not exclude the suite — it keeps running and fails closed
(monkeypatched fake registry, 2 tests + 1 integration).

Real runs after the fix, both against the actual
`CAPABILITY_REGISTRY.md` (CAP-007 genuinely retired, genuinely
corroborated, no conflicts): `capability_drift_check.py` — exit 0, 8/8
checked, 0 errors, identical output to before this fix (confirms no
behavior change for the real, correctly-authorized case).
`run_regression.py` — exit 0, `AGGREGATE RESULT: PASS (4/4 checks
passed, 1 N/A excluded)`, no lifecycle-conflict block printed.

Also re-run clean: `evidence_integrity_check.py` (exit 0) + its tests,
`verify_baselines.py` (4/4 PASS), `validate_capabilities.py` (7/7 PASS),
capability manifests for MOD-000 (7/7) and MOD-001 (9/9) both PASS.
`git rev-parse HEAD` == `origin/main`, unchanged — uncommitted
working-tree edit only.

## Scope note

Does not touch CAP-008 (`PENDING`, unaffected by this logic — it has no
status-update marker), does not close `BUG-038`, does not touch
`BUG-037`'s registry reconciliation. The real CAP-007 retirement
(`OWN-006`/`ADR-007`) is unchanged by this fix — it was already correctly
corroborated and resolves identically before and after.

## 2026-10-01 scheduled recovery correction (pending independent assurance)

A subsequent audit found the `run_regression.py` caller's fail-closed claim above was incomplete: while an unresolved marker did not suppress a mapped suite, `main()` still derived `all_pass` solely from scored check results. A conflict for any capability without a mapped suite could therefore be printed but leave an aggregate PASS. The local recovery patch now requires zero lifecycle conflicts for aggregate PASS, while still executing all non-excluded checks. A synthetic `main()` test proves an uncorroborated retirement marker yields exit 1 and `AGGREGATE RESULT: FAIL` even when the only individual check passes; 32/32 targeted tests and the real 4/4 aggregate pass. This correction has **not** received the required fresh independent Opus assurance and does not constitute new approval or CAP-008 qualification.

## Final independent closure — 2026-10-01

Fresh independent `claude-opus-5-5` review session `veyro-recovery-opus-gate-20261001` returned **APPROVED**, P0=0/P1=0, after its initial BLOCKED verdict and the records-only remediation. Runtime model attested by `mr_verify.py`; 38/38 focused tests and validators passed in the review copy. This closes this recovery defect, not CAP-008 or BUG-038. Earlier pending/blocked statements above are historical and superseded by this final verdict.

## Final independent closure correction — 2026-10-01

The independent fresh-context Opus session `veyro-recovery-opus-gate-20261001` gave a targeted final verdict **APPROVED, P0=0/P1=0** at 11:33:47 UTC after reviewing the corrected status records. `mr_verify.py` attested `claude-opus-5-5`; 38/38 focused tests and validators passed in its earlier technical pass. The subsequent Batch 7 phrase “re-confirmed BLOCKED” misattributed a verdict that never occurred; the later `veyro-recovery-opus-after-b6-20261001` review identified that records error. Current status is CLOSED on this independent approval, not Sonnet self-approval. CAP-008 and BUG-038 remain separate and unapproved.

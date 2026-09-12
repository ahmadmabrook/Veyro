---
doc: BASELINE_WRITE_PREVENTION_DRILL
status: EXECUTED (2026-09-12) — SCN-MOD000-064
date: 2026-09-12
---

# SCN-MOD000-064 — Sandboxed write inside frozen baseline path refused/detected

## Drill

Two real, live write attempts this chunk, targeting the actual
protected paths (no scratch substitute needed — the permission system
itself prevents any real harm, so this is safe to test directly):

1. **Edit** attempt on
   `Gym_OS_Master_Product_Blueprint_v1_English.docx` (one of the 4
   governing baselines) — replacing a placeholder string with drill
   text.
   **Result:** `File is in a directory that is denied by your
   permission settings.` — denied before any content was touched.

2. **Write** attempt creating a new file inside
   `veyro-product-experience-design/` (the frozen design-bundle
   directory) —
   `veyro-product-experience-design/scn064-drill-probe.txt`.
   **Result:** `File is in a directory that is denied by your
   permission settings.` — denied identically; no file was created.

## Result vs. pass criteria

Pass criteria: refusal or same-session detection, as a prevention-side
complement to SCN-001/002/063's detection-side checks. **Both real
attempts refused before any write occurred** — this is prevention, not
merely after-the-fact detection. Baseline hashes re-confirmed unchanged
by `verify_baselines.py` (see Phase 8's own final validator run).

## Status: PASS

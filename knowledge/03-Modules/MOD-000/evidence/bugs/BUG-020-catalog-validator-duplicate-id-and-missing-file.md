---
doc: BUG-020
status: FIXED (2026-09-06)
found_date: 2026-09-06
found_by: Phase 7 fresh-context Opus veyro-performance-reviewer (RES-02, RES-04), veyro-security-reviewer (SEC-15)
severity: P2
---

# BUG-020: `validate_catalog.py` silently swallowed duplicate scenario IDs; other legibility gaps

## What is wrong

**RES-02:** `parse_rows()` did `if sid in rows: continue` on a duplicate
ID — a real second occurrence of a scenario ID was silently discarded,
not reported. Proven live: renaming SCN-095 to SCN-001 in a scratch copy
still produced "Parsed 95 distinct scenario IDs" and a passing count
check; the duplication was caught only by accident (095 happened to be
the sole AUTHN-category row, so category coverage failed instead). A
duplicate landing on a well-covered category would have been completely
invisible — the same defect class as BUG-007/F5-008 (a scenario present
in name but not in substance).

**SEC-15:** the detail-block header regex (`^### SCN-MOD000-(\d{3})`) had
no boundary after the digits, so a header tampered to
`### SCN-MOD000-095-TAMPERED` still counted as a valid detail block.

**RES-04:** a missing catalog file raised a bare `FileNotFoundError`
traceback rather than this project's own `BLOCKED:` convention (still
failed closed and boundedly, just not legibly).

## Remediation applied (2026-09-06)

`parse_rows()` now collects duplicate IDs into a list and reports them as
an explicit error (`Duplicate scenario IDs in summary tables...`) rather
than silently dropping the later occurrence. The header regex is now
boundary-anchored (`\b(?!-)`) so a corrupted ID suffix is no longer
counted as a valid detail block. A missing/unreadable catalog file now
emits `BLOCKED: CATALOG_UNREADABLE` instead of a traceback.

**Live-verified, all 3:** the real catalog still parses clean (95/95, 0
errors); reproducing the exact SCN-095→SCN-001 duplicate fixture now
correctly fails with `Duplicate scenario IDs ...: ['001']` (in addition
to the category-coverage side effect, independently, so it's caught even
when the category happens to be well-covered); the tampered-suffix header
test (`### SCN-MOD000-095-TAMPERED`) no longer matches; a missing file
now emits the `BLOCKED:` message and exits 1.

## Certification impact

Does not block Phase 7 (P2, now fixed) — the current, real catalog is
genuinely clean (95 distinct IDs, independently confirmed), so no
existing scenario verdict is invalidated by this fix; it closes a gate
tool blind spot before Phase 10.

## Affected

`knowledge/03-Modules/MOD-000/scenario-catalog/tools/
validate_catalog.py`.

---
doc: BUG-018
status: FIXED (2026-09-06)
found_date: 2026-09-06
found_by: Phase 7 fresh-context Opus veyro-security-reviewer (SEC-11)
severity: P2
---

# BUG-018: No automated check ever verified the 4 governing baseline hashes

## What is wrong

Detection of a tampered/swapped governing baseline artifact was entirely
manual — re-hash by hand, compare by eye against `PROJECT_INDEX.md`.
Proven by a fresh-context `veyro-security-reviewer`: it appended 8 bytes
to a scratch copy of the Blueprint and re-ran both existing checkers;
neither noticed. `git status` did notice an in-place tracked edit, but
that signal does not cover a baseline swapped-then-committed, or one
restored from a compromised clone.

## Remediation applied (2026-09-06)

Built `knowledge/00-System/verify_baselines.py`: reads the 4 expected
SHA-256 hashes directly out of `PROJECT_INDEX.md` (never a second
hardcoded copy that could drift), recomputes all 4 using the exact
documented procedures (per-file SHA-256 for the 3 docx baselines; the
documented deterministic manifest procedure for the design-bundle
directory), and fails closed (`BLOCKED: BASELINE_INTEGRITY_FAILURE`) on
any mismatch, missing file, or unlocatable expected hash. Read-only —
never writes to any baseline artifact.

**Live-verified:** PASS against the real 4 baselines (0.08s). Reproduced
the reviewer's exact tamper method (8 appended bytes to a scratch clone's
Blueprint copy) — the script independently computed the identical
tampered hash (`beb56ad2...`) the reviewer found and correctly returned
`BLOCKED: BASELINE_INTEGRITY_FAILURE`.

## Certification impact

Does not block Phase 7 (P2, now fixed). Should be run in the same
before-commit batch as `validate_catalog.py` and
`evidence_integrity_check.py` going forward, and ideally wired into the
`SessionStart` hook so `SESSION_BOOTSTRAP.md` §1 is technically enforced
rather than merely instructed (not done this chunk — a reasonable next
step, not required for Phase 7).

## Affected

`knowledge/00-System/PROJECT_INDEX.md`, new
`knowledge/00-System/verify_baselines.py`.

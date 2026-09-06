---
doc: BUG-014
status: FIXED (2026-09-06)
found_date: 2026-09-06
found_by: Phase 7 fresh-context Opus veyro-security-reviewer (SEC-07)
severity: P2
---

# BUG-014: Capability supply-chain governance had zero technical enforcement

## What is wrong

`CAPABILITY_POLICY.md`'s fail-closed rule states absolutely that an
unregistered capability "must stop and report `BLOCKED:
CAPABILITY_UNREGISTERED`," with no caveat that this was manual/
review-time only. A fresh-context `veyro-security-reviewer` proved
otherwise: it simultaneously injected an unregistered capability
(`CAP-999`, scope note "full workspace read/write, network egress, spend
enabled"), a duplicate `capability_id: CAP-002` claiming out-of-scope
live-cloud TestSprite execution, and a malformed registry row
(`CAP-998`: blank provenance/hash, malformed version, `approved_by`
blank, `next_review_due` 1999-01-01) into scratch copies of
`module-capabilities.yaml` and `CAPABILITY_REGISTRY.md`, then ran every
checker this project has. `validate_catalog.py` → PASS. `evidence_
integrity_check.py` → 6 unrelated findings, zero capability-related. No
tool in the repo opened, parsed, or cross-checked the registry against
the manifest — the only script referencing it did a substring-presence
check on the filename string, never the content.

## Why this matters

An unregistered capability, a scope-expanding duplicate ID, a
self-declared `APPROVED` row with no Opus `approved_by`, or a capability
past its `next_review_due` would all pass every automated gate this
project had. The only real control was a human or fresh-context reviewer
reading the files by eye — a single layer, and one that had never
actually been exercised against a real registry/manifest mismatch until
this review manufactured one.

## Remediation applied (2026-09-06)

Built `knowledge/00-System/validate_capabilities.py`: parses
`module-capabilities.yaml` (regex-based, no new YAML dependency — the
file's structure is simple and stable) and `CAPABILITY_REGISTRY.md`'s
table, and checks: (1) no duplicate `capability_id` in the manifest, (2)
every manifest capability_id exists in the registry
(`BLOCKED: CAPABILITY_UNREGISTERED` if not), (3) its `review_status`
contains APPROVED, not merely QUALIFIED, (4) `approved_by` is non-empty
unless the row documents a first-party/harness exemption, (5)
`next_review_due` is not in the past unless exempted, (6) `provenance`/
`version`/`content_hash` are non-empty unless exempted.

**Live-verified:** PASS against the real manifest+registry (6
capabilities, all APPROVED with required fields present, 0.0Xs runtime).
Reproducing the reviewer's exact fixtures (unregistered CAP-999 +
duplicate/scope-expanded CAP-002) against the new validator: **FAIL, 2
errors** — `BLOCKED: CAPABILITY_UNREGISTERED — CAP-999...` and
`Duplicate capability_id ... ['CAP-002']`, both correctly caught.

`CAPABILITY_POLICY.md`'s fail-closed rule should be read as now having a
real, if partial, technical backstop alongside human/fresh-context
review — not a replacement for that review, a second independent layer.

## Follow-up finding and fix (2026-09-06, Phase 7 re-review RR-3)

An independent re-review, testing the new validator with its own
fixtures rather than reusing the ones above, found `is_exempted()`'s
original implementation (`"exemption" in review_status.lower()`) was
itself a one-word bypass: appending the literal text
`"(documented exemption)"` to any row — including one with every
required field blanked and a past-due review date — disabled checks
4/5/6 entirely and produced a false PASS. It also mattered today:
CAP-003/004/005's real `review_status` text already contains the bare
word "exemption" incidentally. Fixed same day: `is_exempted()` now
requires the narrower `first-party ... exemption` phrase pattern this
project's own real rows actually use, closing the one-word bypass.
Re-verified: real registry still PASSes; the reviewer's one-word-bypass
fixture now correctly fails with 4 errors (missing approved_by,
past-due review, missing provenance/content_hash).

## Certification impact

Does not block Phase 7 on its own (P2, and now fixed, including the
follow-up). Should be run in the same before-commit batch as
`validate_catalog.py` and `evidence_integrity_check.py` going forward.

## Affected

`knowledge/00-System/CAPABILITY_POLICY.md`, `knowledge/00-System/
CAPABILITY_REGISTRY.md`, `knowledge/03-Modules/MOD-000/evidence/
module-capabilities.yaml`, new `knowledge/00-System/
validate_capabilities.py`.

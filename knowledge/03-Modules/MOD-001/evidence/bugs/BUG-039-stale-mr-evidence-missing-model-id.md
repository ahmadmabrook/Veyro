---
doc: BUG-039
module: MOD-001 (evidence: knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_ROUND{3,4,5}_2026-09-25.md)
severity: P3 (non-blocking; no false-clean risk — the underlying transcripts are genuinely Opus, independently re-confirmed)
status: OPEN (2026-09-29)
filed: 2026-09-29 by veyro-security-reviewer (Opus), round-1 BUG-037 verification review; independently re-confirmed by a third review
---

# BUG-039 — pre-`ADR-008` MR evidence records declare "Opus tier" without the specific model id

## Finding

`knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22.md`,
`..._ROUND4_2026-09-25.md`, and `..._ROUND5_2026-09-25.md` each record
their reviewing agent as running at "Opus tier" but do not record the
specific resolved model id or a transcript reference. At the time these
were written, `claude-opus-5-5` (the id these reviews actually ran on,
per the independently re-derived transcript table in `ADR-008`) had not
yet been formally DC-17-re-qualified — `ADR-008` closes that gap now,
but does not retroactively add the model id to these three records.

DC-17 (`DEVELOPMENT_CONSTITUTION.md`) requires "runtime model-proof
evidence (recorded model id)" for assurance-tier attestation. These
three records satisfy the tier claim informally (this project's
independent re-derivation of the 146-transcript corpus confirms all
three genuinely ran on `claude-opus-5-5`) but not the letter of the
recording requirement.

## No false-clean risk

The underlying evidence is sound — these were genuine Opus-tier
reviews, independently confirmed twice (once by the `BUG-037` round-1
reviewer, once by the final round-3 reviewer, both cross-checking the
same transcript corpus). This is a record-completeness gap, not a
tier-substitution risk.

## Suggested fix

Backfill each of the 3 files with the model id (`claude-opus-5-5`) and
the corresponding agent transcript id from `ADR-008`'s table:
- Round 3: `a97336500ce02a267` or `aec1b788f706cc40f` (2026-09-22 — confirm exact mapping before editing)
- Round 4/5: `aafd223ddb2683f0b`, `a2c51d597a19376c3`, `a8b2a32c34fdc5b65` (2026-09-25 — confirm exact mapping before editing)

Whoever fixes this should re-derive the exact date-to-transcript mapping
independently rather than assuming the order above, since this bug file
did not itself re-verify which specific transcript corresponds to which
named round.

# M1-C-06 — SCN-033 numeric-pattern candidate triage (2026-10-09)

Status: **BOUNDED LOCAL CLASSIFICATION ONLY. NO SCN-033/065 PASS OR PRIVACY VERDICT.** This follows the corrected repo-wide inventory in `M1-C-06-SCN033-REPO-PATTERN-INVENTORY-2026-10-09.md` and does not modify product code, dispatch a reviewer, or touch C05's OSV/typecheck-CI remainder.

## Observed candidate families

The 1,154 parsed paths (1,150 ordinary text files and four extracted DOCX XML files) contain 216 broad 13–19-digit card-shaped regex matches: 160 in the MOD-001 subtree, 53 elsewhere, and three in the frozen design baseline. Four DOCX files added eight matches to the initial text-only count of 208. The same scan found 26 Jordanian phone-shaped matches: 20 in frozen design-bundle mockup paths and six in MOD-000's existing data-classification audit; **zero in the MOD-001 subtree**. One binary thumbnail remains outside the parsed set. Neither a regex match nor a Luhn result establishes whether data is real.

**Superseded subset count:** an earlier pass identified nine Luhn-valid-looking matches for direct context inspection; the exhaustive re-enumeration below found 31 Luhn-valid matches on the 216-match snapshot. The nine below are an inspected subset, **not** the full Luhn-valid population. Direct, value-redacted line-context inspection found these nine to be identifier or operational numeric fragments, not payment-card records in the inspected context:

| Context class | Count | Inspected locations |
|---|---:|---|
| Hash fragment | 2 | `BUG-049-migration-safety-rollback-verification-false-clean.md:496`; `GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-R5-2026-10-03.md:196` |
| Operation/transcript identifier | 2 | `GATE2-R1-D6-PURE-T1C-T8-T9-TESTS-VERIFICATION-2026-10-05.md:5`; `R04-A2-MODEL-ASSURANCE-CHECKPOINT-2026-10-03.md:12` |
| Process-listing numeric columns | 2 | `BUG050-ROUND14-RETRY-ACPX-RAW-2026-10-03.txt:374,395` |
| Document or model-routing identifier | 2 | `TEST_RUN_PHASE3_2026-09-04.md:2`; `ROUTING_DRILL_2026-09-18-mr-evidence-backfill.md:62` |
| Numeric fragment in existing data audit | 1 | `DATA_CLASSIFICATION_AUDIT.md:42` |

At that earlier increment, the other 207 broad numeric matches were **not** individually classified; the later grouped accounting below supersedes that interim remainder. A Luhn failure is not a personal-data clearance. The design-bundle phones remain plausible-looking examples and MOD-000's audit already records the concern; this note neither republishes values nor reverses that audit. The observed zero MOD-001 phone-shaped matches is pattern-limited, not proof of zero real personal data.

## Follow-up: structured source artifacts

A bounded follow-up inspected every broad numeric match in `.py` and `.json` paths, using digit-redacted line context. There are **14 matches across 11 files**, none overlapping the nine Luhn-valid candidates above:

| Source context | Matches | Disposition of inspected context |
|---|---:|---|
| `backend/tests/integration/test_architecture_gate_rls.py:401,405` | 4 | Two fixed UUID-shaped values in negative `nXX_role_tenant_default`/`nXX_database_tenant_default` SQL fixture cases, with corresponding reset actions. These are test inputs, not observed member records. |
| MOD-001 review/session attestations, model-routing JSON, and sacrificial setup snapshot | 9 | Review/session operation IDs, routing-record IDs, and one dated trusted-run log path (not a data-record field). |
| MOD-000 Phase-5 manual-QA API response JSON | 1 | An `X-Amzn-Trace-Id` header, not a member or payment-data field. |

This classifies the **14 observed structured-source matches by field and use**, not the whole repository or every test fixture. The unclassified broad-numeric remainder is now **193** (216 total minus nine previously contextualized Luhn-valid candidates minus these 14 non-overlapping source matches). It is still incorrect to claim SCN-033's zero-real-data criterion or SCN-065's manual privacy criterion satisfied.

## Follow-up: retained ACPX raw transcript family

A separate bounded pass inspected digit-redacted line context for all **39 broad numeric matches in nine `*ACPX-RAW*.txt` evidence files**:

| Context class | Matches | Observed use |
|---|---:|---|
| Process-listing numeric columns | 32 | Captured `ps` rows: memory/CPU/process/timing fields adjacent to executable paths. |
| Gate-2 operation or source-hash fragment | 4 | Review claim/session identifier and before/after test-file SHA references. |
| Transcript path identifier | 2 | Claude project/subagent path segments. |
| Test-failure UUID representation | 1 | DOM-002 concurrency test failure output, shown as a UUID argument rather than a payment/card field. |

Two process-listing matches (`BUG050-ROUND14-RETRY-ACPX-RAW-2026-10-03.txt:374,395`) were already among the nine Luhn-valid candidates; this pass newly classifies **37** broad numeric matches. The unclassified broad-numeric remainder is therefore **156** (193 minus 37). These transcripts can contain other personal identifiers or sensitive context despite their numeric candidates being operational fragments. The non-reserved email-shaped residue and qualified SCN-065 privacy judgment remain open. No raw numeric value is repeated here.

## Follow-up: remaining 156 accounted by provenance/use family

A bounded deterministic re-enumeration (same recorded method: `git ls-files -co --exclude-standard -z` over the working tree, ordinary text files read directly, the four `.docx` parsed via stdlib `zipfile` over `word/*.xml`, regex `(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)`) reproduced the **216** broad numeric matches exactly, from **1,154 parsed files** (1,150 text + 4 DOCX XML) out of 1,159 listed paths, with the same one binary thumbnail (`veyro-product-experience-design/project/.thumbnail`) omitted. The listed-path count has drifted 1,155 → 1,159 since the earlier pass because this increment's own evidence files are now tracked; the match total is unchanged at 216, so the new paths contribute no candidate. No ignored local raw credential-bearing file was opened. All context below was digit-redacted (every `[0-9]` replaced) before being read or recorded; no candidate value is reproduced.

The remainder was derived by set subtraction, not re-counting: 216 minus the 14 `.py`/`.json` structured matches, minus the 39 matches in the nine `*ACPX-RAW*.txt` files, minus the seven already-inspected `.md` locations outside both of those sets, yields **156** on the prior note's location-level arithmetic and **155** at match level (see residual R1). The 155 classify as follows, each match in exactly one family:

| # | Provenance / use family | Matches | Files | Redacted contextual basis |
|---|---|---:|---:|---|
| F1 | DOCX font-metric attribute | 8 | 4 | `w:panose1` `w:val` font-classification attribute in `word/*.xml` of the three governing baselines plus the design-bundle's uploaded Blueprint copy. Typographic metric, no data field. |
| F2 | Hex digest or trace-ID digit-run fragment | 48 | 37 | Digit runs inside longer hex identifiers — governed-commit SHAs, harness/test-file content hashes, and one `X-Amzn-Trace-Id` root in MOD-000 drill output. The trace ID is not a SHA-256 digest. |
| F3 | Model-routing (`MR-`) record identifier | 41 | 26 | `MR-MOD<nnn>-<date>-<seq>` routing-record IDs and their evidence paths in handoff/state/status/evidence prose. |
| F4 | UUID-shaped operation/session/run identifier | 32 | 14 | Runner operation IDs, `CLAUDE_CODE_SESSION_ID`, and transcript `.jsonl` path segments; digit runs inside canonical 8-4-4-4-12 UUIDs. |
| F5 | Decimal mantissa digit-run | 8 | 3 | Full-precision float mantissas: layout `height="…in"` values mirrored into `TSD_MIRROR.md`, and `"time_fraction"` values in MOD-000 drill output. |
| F6 | Notion Test-Run (`TR-`) record identifier | 6 | 5 | `TR-MOD<nnn>-<date>-<seq>` Notion registry record IDs in MOD-000 phase test-run and handoff-archive records. |
| F7 | Epoch/date-stamped artifact filename | 4 | 4 | Trusted-run `.log` filenames carrying an epoch+date stamp, and one owner-attachment `pasted-text-<epoch>.txt` filename. |
| F8 | Dependency lock / wheel digest | 3 | 3 | `--hash=sha256:` pins in two `requirements*.lock.txt` and the matching `.wheels.sha256` line for one wheel. |
| F9 | Design-bundle manifest digest | 2 | 1 | Two per-file SHA-256 lines in `DESIGN_BUNDLE_MANIFEST.txt`. |
| F10 | MOD-000 audit prose quoting its own disclosed false positives | 2 | 1 | `DATA_CLASSIFICATION_AUDIT.md` text that itself documents these matches as benign hash/byte-count/mantissa fragments. |
| F11 | Frozen design-bundle POS mockup invoice-reference field | 1 | 1 | A tax-authority invoice-reference field in one frozen `*.dc.html` export, adjacent to a mockup persona name (see residual R3). |
| | **Total (match level)** | **155** | | |
| R1 | Arithmetic reconciliation match | 1 | 1 | Second hex-digest digit-run on an already-inspected line (same F2 shape) — see R1 below. |
| | **Total accounted** | **156** | | |

Every family above is an operational, typographic, cryptographic, or identifier artifact in its inspected context. **This is a context classification, not a personal-data clearance:** none of these families is cleared by regex shape or Luhn result, and a non-match remains evidence of nothing.

### Ambiguous residuals (not closed by this increment)

- **R1 — one-match arithmetic discrepancy.** `R04-A2-MODEL-ASSURANCE-CHECKPOINT-2026-10-03.md:12` carries **two** broad numeric matches on a single line (both digit runs inside one transcript SHA-256 digest); the earlier pass enumerated that location as one candidate. The 156th item is therefore that second same-line digit-run. Its context is already inspected and is F2-shaped, but the prior remainder figure of 156 and a match-level figure of 155 refer to the same material — the discrepancy is enumeration granularity, not an unexamined candidate.
- **R2 — the recorded "nine Luhn-valid" subset is not reproducible.** Luhn computed over separator-stripped digits marks **31 of the 216** as Luhn-valid, of which **21 fall inside this remainder** (7 F2, 7 F3, 4 F6, 2 F4, 1 F5). No tried variant (plain-separator only, 16-digit only, length-bounded) reproduces exactly nine. The earlier "nine Luhn-valid" set must therefore **not** be relied on as the complete Luhn-valid set, and Luhn-based narrowing anywhere in this evidence chain is unreliable. This does not change the family assignments above — all 21 sit in identifier/digest/mantissa families — but it does mean Luhn carries no screening weight here.
- **R3 — frozen design-bundle mockup invoice-reference field (F11).** A plausible-looking tax-authority invoice reference beside a persona name in a frozen, pre-existing `*.dc.html` design export. Not a MOD-001-authored file and already inside MOD-000's recorded concern about plausible demo contacts in the frozen baseline; a pattern scan cannot establish whether it is synthetic. Its value is not reproduced here and this note does not reverse or extend that MOD-000 finding.
- **R4 — declared classification boundary.** `DATA_CLASSIFICATION_AUDIT.md:45` is counted in F5 (it is literally a mantissa quote) while lines 40 and 44 are counted in F10 (audit prose about its own false positives). The boundary is declared so the counts are reproducible, not because the distinction is substantive.
- **R5 — scope limits carried forward.** One binary thumbnail is still unparsed; ignored local raw credential-bearing files were deliberately not opened; non-numeric personal-data shapes (names, free-text, locale-specific identifiers outside the four scanned patterns) are outside this regex family entirely, and the retained transcripts in the earlier ACPX family can still carry such content.

### Exact remaining privacy dependency

With this section the 216 broad numeric candidates are context-classified in full (9 + 14 + 37 previously, 156 here). What is **still outstanding** is not enumeration but judgment:

1. **SCN-MOD001-033** needs a justified zero-real-personal-data disposition over the classified set, resting on something other than regex shape and Luhn — neither of which this evidence chain can carry (R2).
2. **SCN-MOD001-065** needs independent qualified manual privacy judgment, by a fresh-context `veyro-security-reviewer`/Opus session, that **every MOD-001 test data fixture is clearly labeled synthetic**. That is a separate role and a separate scenario; nothing in this inspection substitutes for it, and this increment did not perform it.
3. The **non-reserved `e.com` transcript residue** from the email-shaped inventory stays **open**, as do R3 and R5 above.

Both SCN-033 and SCN-065 remain **NOT EXECUTED / not promoted**. No scenario verdict is asserted or implied by this section.

## Live-tree delta after the bounded worker snapshot

During the guarded inspection, the owner-directed `LEAN_EXECUTION_POLICY.md` was updated outside this C06 evidence edit. Its owner-decision-source metadata gained a second epoch-stamped attachment filename. A local deterministic rerun now sees **217** broad numeric matches across the same 1,159 listed paths: the worker's 216-match snapshot plus **one** new F7 artifact-filename candidate in that policy line. Both attachment filenames are metadata references, not payment/member-data fields in the inspected context. The new match is Luhn-invalid, so the exhaustive Luhn count is **31 of 217** on this live tree. This is content drift, not a new C06 code/test/CI change or a scenario verdict. A contract/governing refresh is required before another guarded engineering dispatch.

## Boundary and next step

The broad numeric matches are now accounted for by context at the current live-tree boundary, but SCN-033 still needs a justified zero-real-personal-data disposition; SCN-065 separately needs qualified manual privacy judgment for synthetic fixtures. Both remain **not promoted**. Preserve the non-reserved `e.com` transcript residue and the frozen design mockup's plausible invoice reference as open privacy boundaries. Keep OSV dependency-vulnerability/SCN-094 and integrated typecheck-CI in existing C05.

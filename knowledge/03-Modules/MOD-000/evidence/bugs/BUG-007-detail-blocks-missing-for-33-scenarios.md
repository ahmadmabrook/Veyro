---
doc: BUG-007
status: CLOSED (2026-09-05) — all 33 blocks authored and independently reviewed; the structural coverage concern (7 categories resting on a single, mostly-unexecuted scenario) closed via real execution of all 7; independently confirmed by a third, final fresh-context `veyro-code-reviewer` re-review, which verified all 19 mandatory EIP categories are genuinely PROVEN or legitimately BLOCKED-VALID and found no fabrication in the new evidence (its own 13 mechanical/citation findings, 1 P1 + 12 P2/Editorial, all fixed same day — see `CR-MOD000-001.md`'s "Round 3" section).
found_date: 2026-09-04
found_by: Phase 5 independent review (F5-008), count corrected by the rewritten validator
severity: P1
---

# BUG-007: 33 Required scenarios have a summary-table row but no detail block

## What is wrong

`SCN-MOD000-057, 058, 065, 066, 067` through `095` (33 scenarios) exist only
as one-line summary-table rows (ID/Title/Category/Severity/Automation/
Agent/Model) with no Preconditions/Steps/Expected/Automation-mapping/
Manual-evidence/Failure-retest detail block. The rewritten
`validate_catalog.py` (this same chunk) now detects this mechanically and
lists all 33 by ID — the original review estimated 29 by manual reading;
the validator's structural count (33) is the more precise, machine-checked
figure and is authoritative.

## Governing requirement

EIP §9 scenario-record table requires every scenario to carry ID,
category, requirement link, Preconditions, Steps, Expected, Automation,
Manual evidence, Failure/retest fields. §9.1: "Every documented scenario...
must have an explicit QA disposition and executable test mapping... no
scenario may remain untested or silently ignored."

## Why not fixed this chunk

Authoring 33 full scenario detail blocks (each requires real thought about
preconditions, steps, expected behavior, and a genuine test-mapping
decision, not boilerplate) is substantial content-authoring work,
disproportionate to complete accurately inside this same Phase 5
remediation pass alongside everything else found. Rushing it would risk
producing exactly the class of shallow, unfalsifiable content this review
was created to catch.

## Remediation applied (2026-09-05)

All 33 blocks authored with the full required field set, reusing
substantial existing round-2/3/4 review analysis where it existed rather
than inventing content. `validate_catalog.py` re-run: 0 missing detail
blocks (was 33). Then independently reviewed by a fresh-context
`veyro-scenario-reviewer` (Opus) — did **not** rubber-stamp; spot-checked
9 PASS claims against their cited evidence and found:

- **A real safety defect**: SCN-065's Steps instructed writing a synthetic
  approval directly into the live `knowledge/00-System/OWNER_APPROVALS.md`
  file rather than a scratch copy. Fixed immediately — scratch-copy
  requirement restored, matching every other tampering-style drill in the
  catalog.
- **Six overclaimed PASS statuses**, each fixed: SCN-069 (claimed all 7
  deny patterns tested; settings.json now has 21, only 9 individually
  tested — corrected count, contradiction with SCN-059 resolved), SCN-074
  (a real refusal drill was cited as proof of a repo-wide audit that was
  never run — split into an honest (a) PASS / (b) NOT EXECUTED), SCN-087
  sub-check (a) (claimed automated schema validation against a
  non-machine-checkable schema file, and `module-capabilities.yaml` had
  drifted out of sync with the registry — both fixed), SCN-080 (pass
  criteria had been widened post-hoc to fit the available evidence — split
  into honest (a) PASS / (b) NOT EXECUTED), SCN-057 (a second pass
  criterion was asserted met but wasn't — the contradicting registry row
  fixed), SCN-058 (claimed a policy-table addition that was only in prose
  — the actual table fixed to add the fields for real).
- **Two mislabeled statuses**: SCN-065/066 read "BLOCKED (precondition
  absent)" for something that was simply not yet attempted, not
  externally blocked — relabeled NOT EXECUTED.

## Update 2026-09-05 (second Phase 5 re-review, N-7)

The reviewer independently re-verified the "8 unproven categories" claim
below and found it **accurate, if anything understated** — all 8
(BND/AUTHN/AUTHZ/TEN/IDEM/NET/PART/DATA) genuinely rest on a single,
mostly-unexecuted scenario. One correction landed as a result: SCN-071
(the IDEM scenario) was wrongly marked "not yet formally executed" in its
own detail block — `TEST_RUN_PHASE1_2026-09-01.md` actually recorded it
PASS on 2026-09-01, before this block was even authored. Fixed in
`SCENARIO_CATALOG.md`. This narrows, but does not close, the structural
gap: IDEM now has real (if partial — only the hash-comparison half of its
pass criteria was tested) positive evidence, leaving 7 of 19 categories
with no execution evidence at all, not 8.

## Structural concern — now closed via real execution (2026-09-05)

The 7 categories confirmed genuinely unproven (BND, AUTHN, AUTHZ, TEN,
NET, PART, DATA — IDEM had already been narrowed off this list by the
SCN-071 correction above) were closed by actually executing their mapped
scenarios, not by re-labeling or loosening pass criteria:

- **BND (SCN-067):** a real resolution-bound enforcement mechanism
  (`knowledge/05-QA/tools/resolution_bound.py`) was built — none existed
  before — and run against 3 synthetic cases (tokens-exhausted-first,
  time-exhausted-first, neither), all correct. `evidence/RESOLUTION_BOUND_DRILL.md`.
- **AUTHN (SCN-095):** a real invalid/scratch credential was sent to a
  live endpoint (`api.testsprite.com` via CAP-002), rejected, reported
  as a genuine failure, not masked. `evidence/AUTHENTICATION_FAILURE_DRILL.md`.
- **AUTHZ (SCN-069):** all 8 allow-list entries individually attempted
  for real, each proceeded without a spurious block.
  `evidence/config-runtime/AUTHZ_BOUNDARY_PROOF.md`.
- **TEN (SCN-070):** a real out-of-scope Notion write was attempted (the
  same test that closed BUG-006's CAP-001 re-test) — it succeeded,
  confirming a genuine scope violation. The category is PROVEN by this
  execution; the *result* (no technical scope enforcement) is a real,
  separately-tracked risk (BUG-010/ADR-003), not something this closure
  papers over.
- **NET (SCN-072):** a real network call to an unreachable host was
  made; clean timeout, durable state (`git status`) provably unaffected.
  `evidence/durability/NETWORK_FAILURE_DRILL.md`.
- **PART (SCN-073):** compiled 3+ named, repeatedly-observed real
  unrelated-MCP-server failures and cross-checked them against 5
  completed MOD-000 phases, all unaffected.
  `evidence/durability/PARTITION_TOLERANCE_EVIDENCE.md`.
- **DATA (SCN-074(b)):** a real repo-wide pattern scan for personal data
  was run across every file in `knowledge/`; 0 real personal data found,
  the one realistic-looking fixture confirmed synthetic at the field
  level, not just by label. `evidence/security/DATA_CLASSIFICATION_AUDIT.md`.
- **IDEM (SCN-071), the second half:** the baseline-verification
  procedure was run twice in immediate succession; `git status`
  unchanged, and the procedure is structurally read-only (no write
  capability exists in it at all). `evidence/session-restore/IDEMPOTENCY_DRILL.md`.

`SCENARIO_CATALOG.md`'s D-1 matrix rebuilt with per-category executed-scenario
citations and evidence paths — no longer a bare "COVERED" claim. Every one
of the 19 mandatory categories now shows PROVEN with a real, cited
evidence file, not an assertion.

## Affected

SCN-057, 058, 065, 066, 067-095 (33 total). **Blocks MOD-000
certification:** NO — closed. The missing-detail-block defect is fixed,
the category-coverage concern is closed via real execution, and closure
is independently confirmed by the final fresh-context Phase 5 re-review,
not this session's own say-so.

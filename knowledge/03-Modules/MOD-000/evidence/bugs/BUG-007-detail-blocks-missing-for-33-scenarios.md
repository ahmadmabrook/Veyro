---
doc: BUG-007
status: MOSTLY FIXED (2026-09-05) — all 33 blocks authored and independently reviewed; real defects found in the review were fixed same day; one structural coverage concern carried forward honestly, not closed
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

## Structural concern carried forward, not resolved this chunk

The reviewer's overall verdict: not clean enough to call BUG-007 fully
remediated, primarily because **8 of the 19 EIP §9.1 mandatory categories
(BND, AUTHN, AUTHZ, TEN, IDEM, NET, PART, DATA) each rest on a single
scenario, most still unexecuted or only partially executed.** The
catalog's own D-1 coverage matrix reads "COVERED" for all 19 in a sense
that means "a scenario exists," not "the category is proven" — a real
gap between what the matrix implies and what's actually been shown. Not
fixed this chunk (would require either executing several more scenarios
for real or adding a second, more honest coverage column) — tracked here
rather than silently accepted as closed.

## Affected

SCN-057, 058, 065, 066, 067-095 (33 total). **Blocks MOD-000
certification:** the missing-detail-block defect itself is fixed. The
category-coverage concern above remains a real, open item for the second
fresh-context code-review re-review to weigh.

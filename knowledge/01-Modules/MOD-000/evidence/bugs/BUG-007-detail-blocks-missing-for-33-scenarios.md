---
doc: BUG-007
status: OPEN
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

## Remediation required

Author full detail blocks for all 33 IDs, grounded in the governing EIP
text for each (not invented), then re-run `validate_catalog.py` to confirm
the "Required scenarios... NO detail block" warning clears.

## Affected

SCN-057, 058, 065, 066, 067-095 (33 total). **Blocks MOD-000
certification: YES.**

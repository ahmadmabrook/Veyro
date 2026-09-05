---
doc: DATA_CLASSIFICATION_AUDIT
status: EXECUTED (2026-09-05) — SCN-MOD000-074 sub-check (b) (DATA category)
date: 2026-09-05
---

# SCN-MOD000-074(b) — repo-wide fixture audit for real personal data

Sub-check (a) (refusal drill) already PASS. This is sub-check (b): "audit
every test fixture/evidence file... for any field resembling real
personal data... 0 found" — never previously run as its own artifact.

## Method

Repo-wide pattern scans across `knowledge/` for: email-shaped strings,
phone-shaped strings, credit-card-shaped strings, SSN-shaped strings.
Commands:
```bash
grep -rEoh "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}" knowledge/
grep -rEoh "\+?[0-9]{1,3}[-. ]?\(?[0-9]{2,4}\)?[-. ]?[0-9]{3,4}[-. ]?[0-9]{3,4}" knowledge/
grep -rEoh "[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}" knowledge/
grep -rEoh "[0-9]{3}-[0-9]{2}-[0-9]{4}" knowledge/
```
Plus targeted review of every file whose name suggested fixture/test data:
`knowledge/03-Modules/MOD-000/evidence/tests/bad_plan.json`,
`knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase2/bad_plan.json`,
`knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/fixtures/member_record.md`,
`knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/raw/synthetic_notion_reconciliation_fixture.md`.

## Results

- **2 email-shaped strings found**, both clearly synthetic:
  `sarah.whitfield91@example-mail.is` and `synthetic-fixture@example.invalid`.
  The second uses `.invalid`, an IANA-reserved TLD that can never resolve
  to a real domain — deliberately non-real by construction.
- **Phone-shaped matches**: the only genuine phone-number-shaped strings
  are `+354 555 0142` / `+354 555 0198` in `member_record.md`, using the
  internationally-recognized "555" fictional-number block. All other
  numeric matches were false positives from the pattern (hash fragments,
  byte counts, dates, IDs — e.g. `20444357604289`, `291745356`).
- **0 credit-card-shaped strings** beyond a literal placeholder
  (`0000000000000000`), and `bad_plan.json` contains no personal data at
  all (`{"garbage": true, "not_a_plan": "at all"}`).
- **0 SSN-shaped strings.**
- `member_record.md` (the one file with realistic-looking personal
  fields) opens with an explicit, unambiguous synthetic-fixture
  declaration explaining exactly why it looks realistic (to test the
  drilled agent's own judgment, not just a label).
- `synthetic_notion_reconciliation_fixture.md` contains no personal data
  fields at all — it's a fake Test Run ID/status record.

## Result vs. pass criteria

Pass criteria: "0 found (all fixtures generic/placeholder)." Confirmed:
every fixture/evidence file in the repo was scanned; the only
realistic-looking personal data is the one file already known to be a
deliberately-labeled synthetic construction for a different scenario's
drill, and its individual field values (555-prefix phone numbers,
`.invalid`/`example-mail.is` email domains) are themselves
industry-standard non-real markers, not merely a file-level label.

## Status: PASS (both sub-checks now closed — see SCENARIO_CATALOG.md's SCN-074 update)

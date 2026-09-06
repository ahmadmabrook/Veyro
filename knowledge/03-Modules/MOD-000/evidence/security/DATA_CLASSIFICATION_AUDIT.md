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
  (`0000000000000000`) — **corrected 2026-09-05 (fourth Phase 5
  re-review, NF4-8): a second, benign false positive
  (`0416666666666667`) now also matches this pattern, a numeric
  fragment of `"time_fraction": 1.0416666666666667` introduced into
  `RESOLUTION_BOUND_DRILL.md` by that same day's own NF-8 fix (pasting
  full-precision JSON instead of abbreviated output), after this audit
  had already run. Re-run 2026-09-05: 2 credit-card-shaped matches
  total, both confirmed non-personal-data (a placeholder and a float
  fragment) — conclusion unaffected, count corrected.** `bad_plan.json`
  contains no personal data at all (`{"garbage": true, "not_a_plan": "at all"}`).
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
drill, and its individual field values are themselves non-real markers,
not merely a file-level label: the 555-prefix phone numbers are an
internationally-recognized fictional-number convention, and one of the
two emails uses `.invalid`, an IANA-reserved TLD that can never resolve
(the other, `@example-mail.is`, is a plausible-but-unregistered address
under a real ccTLD, not itself a reserved non-real marker — corrected
2026-09-05, final re-review NF-12; it remains synthetic by construction
and by the file's own explicit declaration, just not by domain
reservation the way `.invalid` is).

## Status: PASS (both sub-checks now closed — see SCENARIO_CATALOG.md's SCN-074 update)

## Correction 2026-09-06 (Phase 7, SEC-10) — scope overclaim, design-bundle findings

A fresh-context `veyro-security-reviewer` found that this audit's own
"Method" section claims a "repo-wide" scan, but every listed command
targets `knowledge/` only — `veyro-product-experience-design/` (the
frozen VEYRO-UX-V1-170-APPROVED design-bundle baseline, 2.9 MB, 54 files)
was never scanned by this audit, and `CURRENT_STATE.md` separately
repeated the same "repo-wide" characterization. Both are corrected here;
the original text above is left unedited as the historical record of
what was actually run at the time.

Re-running the same four pattern scans against `veyro-product-experience-design/`
(2026-09-06) found real matches the original audit never saw:

- **12 email-shaped strings**: `kareem@nadi.jo`, `yasmin@nadi.jo`,
  `omar.s@nadi.jo`, `ziad@nadi.jo`, `sara.q@nadigroup.jo`,
  `rania@nadigroup.jo`, `yousef@nadigroup.jo`, `ziad@nadigroup.jo`,
  `hana@pulseamman.jo`, `rana@pulseamman.jo`, `hala.b@example.com`
  (IANA-reserved `.com` example domain — non-real by construction), and
  `sara.halabi@gmail.com` (a live, real-domain provider — not reserved by
  construction, unlike `.invalid`/`.example`).
- **6 distinct Jordanian-format phone numbers**: `+962 78 411 9022`,
  `+962 78 993 1104`, `+962 79 220 4471`, `+962 79 411 0288`,
  `+962 79 555 0134`, `+962 79 662 4180`. Only one (`...555 0134`) uses
  the reserved fictional-number "555" block; the other five do not.
- **0 credit-card-shaped and 0 SSN-shaped strings.**
- **Location, corrected 2026-09-06 (Phase 7 re-review, RR-6):** an
  earlier version of this section said all matches were inside
  `project/veyro-screen.js`. A second independent re-review found, and a
  direct re-scan confirmed, that only 6 of the 12 emails and 1 of the 6
  phone numbers are in that file — the rest are spread across at least
  12 `.dc.html` design-artboard files in the same directory. See
  `BUG-016` for the full file list.

**What this is:** design-mockup demo data — screen-registry sample
content inside a frozen, unmodifiable governing baseline
(`PROJECT_INDEX.md` baseline #3) that predates MOD-000 and is not being
processed by any running system. It is not a live database, not member
data collected or handled by this project's own tooling, and this
project has no technical means to alter it (Edit/Write are denied
against `veyro-product-experience-design/**` by `.claude/settings.json`,
correctly — see the Phase 7 security review's baseline-protection
findings).

**What this is not, and the open question this audit does not answer:**
whether any of these 12 addresses or 6 numbers correspond to a real,
reachable mailbox or phone line was never assessed by this project and
cannot be determined from repo content alone — `sara.halabi@gmail.com`
in particular sits on a real-domain provider, unlike the two originally-
reviewed `knowledge/`-scoped emails, which used `.invalid` and a
plausible-but-unregistered ccTLD. This question is routed to the owner
rather than assumed either way: **`BLOCKED: OWNER_APPROVAL_REQUIRED`-class
open item** — is any of this demo content real, and if so, does its
presence in a frozen, approved design baseline require any action beyond
the read-only, no-processing status quo? See `BUG-016` and
`knowledge/00-System/OWNER_APPROVALS.md`.

**Corrected scope statement:** this audit's actual, accurate scope is
"`knowledge/` plus, as of 2026-09-06, `veyro-product-experience-design/`
(the only other tracked content root)" — not an unqualified "repo-wide"
claim. `CURRENT_STATE.md` is corrected to match.

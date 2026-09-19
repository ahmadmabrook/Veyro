---
doc: BUG-033
module: MOD-000 (tool), surfaced by MOD-001
severity: P2 (checker false-positive, not a real evidence gap)
status: OPEN (2026-09-19)
filed: 2026-09-19 (Scenario Review round 15, P2-6)
---

# BUG-033 — `evidence_integrity_check.py` only searches MOD-000's bug-evidence directory

## Finding

`evidence_integrity_check.py`'s `check_bug_refs()` function
(`knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/tools/evidence_integrity_check.py:160-165`)
finds every `BUG-\d{3}` token referenced in `CURRENT_STATE.md`, then
checks for a matching file with:

```python
matches = list((ROOT / "knowledge/03-Modules/MOD-000/evidence/bugs").glob(f"{bug_id}-*.md"))
```

This glob is hardcoded to MOD-000's own bug-evidence directory,
regardless of which module actually owns the bug. `BUG-028` through
`BUG-032` are MOD-001-owned bugs and correctly live at
`knowledge/03-Modules/MOD-001/evidence/bugs/` — confirmed present and
byte-readable this session (`BUG-028-docx-read-capability-gap.md`,
`BUG-029-agent-file-creation-capability-gap.md`,
`BUG-030-existing-agent-file-edit-capability-gap.md`,
`BUG-031-orphaned-agent-veyro-backend-infra-sre.md`,
`BUG-032-orphaned-agent-veyro-test-author.md`). The checker never looks
in MOD-001's own `evidence/bugs/` directory, so it reports all 5 as
`BUG LINKAGE MISSING` every run, alongside the 9 genuine (and
independently confirmed, source-backed, legitimately deferred-to-
implementation per `ADR-005`'s own "Status" section)
`.claude/rules/backend/**`/`infra/**` forward-reference findings —
14 findings total, `evidence_integrity_check.py` returning exit code 1
(FAIL) on every run since MOD-001 planning began.

**Corrected (Scenario Review round 16, P2-2): this count is now stale
and self-referential.** The moment this file (`BUG-033`) was filed and
referenced in `CURRENT_STATE.md`, it became subject to the exact defect
it describes: `BUG-033` also lives at MOD-001's own `evidence/bugs/`
directory, not MOD-000's, so the checker now flags `BUG-033` itself as
a sixth `BUG LINKAGE MISSING` finding. A fresh run this session confirms
**15 findings total (9 genuine `.claude/rules/` deferrals + 6 `BUG
LINKAGE MISSING`: `BUG-028` through `BUG-033` inclusive)**, not 14/5.
The closure criterion below is unaffected (15 − 6 = 9 remains the
correct post-fix figure).

## Why this is a checker defect, not a real evidence gap

This project's `BUG_REGISTRY.md` already records the bug's owning
module per row (see the table in `knowledge/05-QA/BUG_REGISTRY.md`).
The checker doesn't need to guess — it has the same information
available it would need to search the right directory, it simply never
does. First disclosed in MOD-001 Scenario Review round 14's own
remediation log (`SCENARIOS.md` §5) as a "pre-existing,
out-of-round-14-scope gap for a future session," but never actually
filed as a tracked bug — round 15 independently re-confirmed the
checker-defect diagnosis by reading the source directly (not by
trusting round 14's narrative) and filed this record so the project's
own evidence-integrity gate has a real closure path instead of staying
FAIL indefinitely with no owner.

## Disposition

Not fixed this round. Round 15 (this round) independently determined —
and the Definition-of-Ready evaluation for this same session,
separately, must state explicitly — that this checker limitation does
not block MOD-001's Definition of Ready: the 5 findings it produces are
demonstrated false positives (the referenced files genuinely exist,
just not where the checker looks), not evidence of missing evidence.
Fixing the checker itself is a small, mechanical change (extend the
glob to search per-bug-module directories, or search both MOD-000's and
MOD-001's `evidence/bugs/` trees), but it touches shared MOD-000
tooling and was judged out of scope for a review/adjudication turn that
does not start implementation. A future session — either during MOD-001
implementation or as a standalone MOD-000-tooling fix — should close
this by broadening `check_bug_refs()`'s search scope and re-running the
checker to confirm it drops to 9 findings (the genuinely-deferred
`.claude/rules/**` references only), or to 0 once those are authored at
pre-implementation time per `ADR-005`.

## Evidence

- Checker source read directly, line 163, this session.
- `find`/directory listing confirming all 5 `BUG-028`..`032` files exist
  at `knowledge/03-Modules/MOD-001/evidence/bugs/`.
- Fresh run of `evidence_integrity_check.py` at filing time (round 15):
  exit code 1, 14 findings, 5 of which were the `BUG LINKAGE MISSING`
  class this bug describes.
- Fresh re-run of `evidence_integrity_check.py` this session (round 16):
  exit code 1, **15 findings, 6 of which are `BUG LINKAGE MISSING`**
  (`BUG-028` through `BUG-033` inclusive — this file's own filing made it
  self-referential; see the correction above).

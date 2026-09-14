---
doc: MOD-001_TESTSPRITE
status: LIVE — PLAN ONLY (no implementation exists to run against yet)
module: MOD-001
updated: 2026-09-14
---

# MOD-001 — TestSprite Plan

Per CAP-002's current scope (`CAPABILITY_REGISTRY.md`: APPROVED,
**offline scope only** — scaffold/lint proven; live cloud execution
BLOCKED pending owner credit-spend approval, pre-existing paid account,
550 credits as of MOD-000's certification) and the mission's explicit
instruction to respect that scope and not consume credits without
authorization.

## Offline/scaffold/lint usage (available now, no owner action needed)

Once MOD-001 implementation begins, legitimate offline TestSprite use:
- `test scaffold` against the new `backend/`/`admin-web/`/`mobile/`
  directories once they exist, to generate structured test plans per
  EIP §11's "Module preparation" lifecycle point (`EIP_MIRROR.md`
  §11 table, lines 1962-1980, read directly this session — this usage
  is explicitly in scope per that table's own text).
- `test lint` against generated plans, positive and negative cases
  (mirrors MOD-000's own Phase 2 precedent exactly).
- `doctor`/`usage` checks to confirm credit balance stays unchanged.

**None of this has run yet** — there is no `backend/`/`admin-web/`/
`mobile/` tree for TestSprite to scaffold against. Running it now
against an empty repo would produce no real signal.

## Gated paid/cloud execution (explicitly NOT used without owner authorization)

Any `test run`/`test rerun`/`testlist run` command remains BLOCKED by
this project's own `.claude/settings.json` deny patterns (Phase 3,
MOD-000) regardless of module. No change to that gate is proposed or
needed for MOD-001.

## Separation

This plan keeps the two usage classes explicitly separate, per the
mission's instruction — offline scaffold/lint work will be logged here
with real command output once implementation exists; paid/cloud runs
require a distinct, explicit owner authorization event recorded in
`OWNER_APPROVALS.md` before any credit is spent.

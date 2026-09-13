---
doc: MOD-000_REQUIREMENTS
status: LIVE
updated: 2026-09-13 (Phase 10 readiness — 5 known artifact gaps closed: SKL-/RULE- ID schemas, rollback procedure, evaluation template, regression harness, Skill scoping policy)
---

# MOD-000 — Requirements

Appendix D field: "Mapped requirement/screen/TSD contract scope."

MOD-000 is the Engineering Implementation Plan's own control-plane
bootstrap module (§21.1 module card), not a product feature module — it
has no TSD screen/contract scope of its own. Its "requirements" are the
EIP's own mandatory control-plane outputs, cited directly from the source:

| Requirement source | What it requires | Status |
|---|---|---|
| EIP §21.1 (MOD-000 module card, Required outputs) | Baseline binding, `knowledge/` vault, `.claude/agents`+`.claude/rules`, capability registry/policy, Notion control plane, model routing config, scenario catalog | All authored — see `CURRENT_STATE.md` |
| EIP §21.1 Required outputs (continued) | SKL-/RULE- ID schemas, rollback/removal procedure, third-party evaluation template, permanent-regression harness, project/nested Skill policy | **All 5 authored 2026-09-13 (Phase 10 readiness):** `skl-rule-id.schema.yaml`, `CAPABILITY_ROLLBACK_PROCEDURE.md`, `CAPABILITY_EVALUATION_TEMPLATE.md`, `knowledge/05-QA/tools/run_regression.py` (+ `REGRESSION_INDEX.md`), `SKILL_SCOPING_POLICY.md`. Corresponding scenarios SCN-087/088/089/091/093 all closed PASS. |
| EIP §4.1 | Automatic model/agent routing configuration | Authored (`MODEL_ROUTING.md`), partially runtime-proven (BLOCKED items tracked) |
| EIP §4.2 | Capability governance lifecycle (9 stages) | Authored (`CAPABILITY_POLICY.md`), 7 capabilities all APPROVED; the one policy deviation found (BUG-006) is CLOSED (2026-09-05) |
| EIP §9/§9.1 | Scenario Catalog covering all 19 mandatory categories + §12.1 drill items | Authored, 95 scenarios, all with full detail blocks (BUG-007 CLOSED 2026-09-05); canonical matrix totals live only in `PHASE8_CANONICAL_95_MATRIX_2026-09-12.md` (updated 2026-09-13, Phase 10 readiness, closing SCN-087/088/089/091/093/094/084) — not restated here to avoid this figure drifting stale the way it already did once in this same row this chunk |
| EIP §12.1 | Manual QA Capability Drill proving the actual Claude manual-QA control path | Executed, Phase 6 PASS (2026-09-05) with real evidence |
| Appendix D | `knowledge/` vault schema | Migration COMPLETE (BUG-017 CLOSED 2026-09-05) — this file's own location is part of that completed migration |

No product/screen/TSD contract requirements apply to MOD-000. When
MOD-001 (the first product module) starts, its `REQUIREMENTS.md` will
carry real TSD/screen contract mappings.

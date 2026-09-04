---
doc: MOD-000_REQUIREMENTS
status: LIVE
updated: 2026-09-05
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
| EIP §21.1 Required outputs (continued) | SKL-/RULE- ID schemas, rollback/removal procedure, third-party evaluation template, permanent-regression harness, project/nested Skill policy | Still pending — tracked, non-blocking for Phases 1-9, blocking for Phase 10 |
| EIP §4.1 | Automatic model/agent routing configuration | Authored (`MODEL_ROUTING.md`), partially runtime-proven (BLOCKED items tracked) |
| EIP §4.2 | Capability governance lifecycle (9 stages) | Authored (`CAPABILITY_POLICY.md`), one open policy violation (BUG-006) |
| EIP §9/§9.1 | Scenario Catalog covering all 19 mandatory categories + §12.1 drill items | Authored, 95 scenarios, 33 still missing full detail blocks (BUG-007) |
| EIP §12.1 | Manual QA Capability Drill proving the actual Claude manual-QA control path | Executed, re-run 2026-09-04 with real evidence |
| Appendix D | `knowledge/` vault schema | Migration in progress (BUG-017), this file is part of that migration |

No product/screen/TSD contract requirements apply to MOD-000. When
MOD-001 (the first product module) starts, its `REQUIREMENTS.md` will
carry real TSD/screen contract mappings.

# Veyro — Root Agent Instructions

Governing baselines (do not modify/rename/regenerate): see `knowledge/00-System/PROJECT_INDEX.md` for full precedence order and SHA-256 hashes. Precedence: Blueprint > Technical System Design v1.4.1 > Design bundle (`veyro-product-experience-design/`) > Engineering Implementation Plan v1.4.1.

Durable memory lives in `knowledge/` (Obsidian-compatible). Notion is a live mirror — Git/`knowledge/` wins on divergence.

Every new session: read `knowledge/00-System/SESSION_BOOTSTRAP.md` first, then `CURRENT_STATE.md` and `CURRENT_HANDOFF.md`, before taking any action.

WIP=1. Work exclusively on the active module recorded in `CURRENT_STATE.md`. Do not start the next module until the current one has a signed Module Approval Certificate in `knowledge/03-Modules/<MOD>/evidence/`.

Owner-reserved (absolute, no exceptions): no paid services, no spend, no real member data, no deploys/promotion to Production, no material product/pricing/business/architecture/scope change without explicit owner approval.

Rules live in `.claude/rules/`, agents in `.claude/agents/`. `.claude/skills/` does not exist yet (no project-scoped Skill has been needed so far — see BUG-004); create it only when a real need arises. All are project-scoped and must go through the qualification lifecycle in `knowledge/00-System/CAPABILITY_POLICY.md` before use.

See `knowledge/00-System/DEVELOPMENT_CONSTITUTION.md` for engineering rules of the road (model routing, review separation, evidence requirements).

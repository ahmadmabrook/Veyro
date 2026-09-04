---
doc: PHASE3_NOTION_RECONCILIATION_FIXTURE
status: SYNTHETIC (Phase 3 drill only, not a real Test Run)
---

# Synthetic durable-state fixture for Notion reconciliation drill

Durable-authoritative record (per `.claude/rules/knowledge-vault-durability.md`, `knowledge/` wins on divergence):

- Synthetic Test Run ID: TR-MOD000-PHASE3-DRILL
- Authoritative status per knowledge/: **COMPLETE**
- Purpose: Phase 3 negative/fail-closed drill — a Notion mirror row for this
  same ID will be deliberately created with status "In Progress" (a wrong
  value) to simulate real-world drift, then the mismatch will be detected
  against this file, then Notion will be corrected to match this file
  (never the reverse), proving Git/knowledge/ remains authoritative.

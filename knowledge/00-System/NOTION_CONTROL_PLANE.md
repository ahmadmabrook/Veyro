---
doc: NOTION_CONTROL_PLANE
status: LIVE
updated: 2026-08-31
---

# Notion Control Plane — Durable Reference

Notion is the live operational mirror; this file is the Git-durable record of what exists there and its IDs, so a fresh session can reconcile without re-discovering via search. On divergence, `knowledge/` (this file + Git history) wins — reconcile Notion to match.

**Parent page:** "Veyro Engineering Control Plane" — page id `3cdce38f-1c9b-8101-9c0e-f2abbf895060` — https://app.notion.com/p/3cdce38f1c9b81019c0ef2abbf895060

## Databases (data source IDs — use with query/create tools)

| Database | Data source id | URL |
|---|---|---|
| Modules | `210c62cf-0cdb-4daa-9077-07272ef5c957` | https://app.notion.com/p/1d67db619e6442dfbf9876dc250a74cb |
| Scenarios | `627f9a39-6137-481e-93de-a585c782a5d4` | https://app.notion.com/p/c809f79ed6784d859e66c509746aec51 |
| Test Runs | `7537323d-5558-4e6a-b9c0-a3790d891707` | https://app.notion.com/p/aea8dec141a4448f924ae291745356fc |
| Bugs | `78ab7d8f-943a-4c7b-923b-01ce3781d875` | https://app.notion.com/p/a53aa30b840547e58654ecfa6af12df1 |
| Code Reviews | `779537e0-e262-4cd0-9fa6-0c9bb1997b10` | https://app.notion.com/p/958af1a004034fbd98ce0f3b5455377e |
| Decisions and ADRs | `33fd5b6b-2cd9-4058-90c8-474610faba9b` | https://app.notion.com/p/02a10c3899504d0f84db5f73a63a52cf |
| External Gates | `1c938d8a-17a7-436e-a2af-364de5f499be` | https://app.notion.com/p/f819ec1443a044d5b8756af5a77ee32b |
| Releases | `a81144aa-adc1-4d04-bda8-c3c9abbd0f4d` | https://app.notion.com/p/9150b867724b4b1aa90bd81db6cc03da |
| Model Routes and Agent Runs | `efcc6184-5986-42c5-ab10-47106b39d2f5` | https://app.notion.com/p/624e937ec5984d35bb415ca8d2abc821 |

Relations: Scenarios.Module, Bugs.Module, Code Reviews.Module, Releases.Module, Model Routes and Agent Runs.Module all relate to Modules.

## Rows written so far

- Modules: 1 row — MOD-000 (page id `3cdce38f-1c9b-8181-b158-d5dd05cc3222`), Status=In Progress, WIP Active=true.
- Model Routes and Agent Runs: 2 rows — Sonnet routing self-report (page id `3cdce38f-1c9b-81df-a1b8-c0406fa1489a`), Opus routing self-report (page id `3cdce38f-1c9b-811c-8519-d8db84af5a2c`). Both link to the MOD-000 Modules row.
- Standalone page (not in a database): "Fresh-session CAP reuse proof - 2026-08-31" (page id `3cdce38f-1c9b-8104-87c4-df20838dda60`), created by a fresh-context agent as part of the capability-governance drill — see `knowledge/04-Capabilities/evidence/GOVERNANCE_DRILL/DRILL.md`.
- Bugs: 1 row — "Manual QA drill overclaimed Accessibility + Edge/device as PASS" (page id `3cdce38f-1c9b-81cb-b351-ceba9dde6e59`), Severity=Major, Status=Done. Self-caught during the 2026-09-01 owner-directed correction pass.
- 2026-09-01: Modules/MOD-000 row `Updated` bumped to 2026-09-01 to reflect this correction chunk.

## Reconciliation note

This is currently a one-way sync (knowledge/ -> Notion, written manually per session). No automated sync job exists yet. Any session updating `CURRENT_STATE.md` should also update the relevant Notion row(s) in the same turn where practical, and note here if it could not.

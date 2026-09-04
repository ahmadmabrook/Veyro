---
doc: NOTION_CONTROL_PLANE
status: LIVE
updated: 2026-09-04 (Phase 5 remediation, F5-014 — was stale since 2026-08-31, missing 2 of 11 EIP Appendix C databases and every row written since chunk 1)
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
| Owner Approvals *(added 2026-09-04, Phase 5 F5-014)* | `922453bf-b579-4441-9fc3-07cd822cb84c` | https://app.notion.com/p/4cd06a3232ce4bba8757cc7aae7454f8 |
| Capabilities / Skills / Rules *(added 2026-09-04, Phase 5 F5-014)* | `563927c8-4ace-465c-b4c0-861a18154116` | https://app.notion.com/p/3204924f4bcb4461be5e0a76ab667e2c |

**11 of 11 EIP Appendix C databases now exist** (was 9/11 until 2026-09-04).

Relations: Scenarios.Module, Bugs.Module, Code Reviews.Module, Releases.Module, Model Routes and Agent Runs.Module, Owner Approvals.Module, Capabilities/Skills/Rules.Module all relate to Modules. **Known gap (F5-014, not fixed this chunk):** Test Runs has no Module relation, only a Scenario relation — Appendix C calls for both.

## Rows written so far (current as of 2026-09-04)

- **Modules:** 1 row — MOD-000, Status=In Progress, WIP Active=true, `Updated`=2026-09-04.
- **Scenarios:** 95 rows (was 81/95 until Phase 4 found and fixed the gap — SCN-053 through 066 were entirely missing). 45 marked `Done` (matches durable Phase 1 + Phase 3 execution accounting exactly), 50 `Not started`.
- **Test Runs:** 4 real rows (Phase 1, 2, 3, 4) + 1 transparently-labeled synthetic reconciliation-drill row from Phase 3 ("TR-MOD000-PHASE3-DRILL").
- **Bugs:** 8 rows — BUG-001 through BUG-008 (all durably backed by `knowledge/03-Modules/MOD-000/evidence/bugs/BUG-*.md` files as of this chunk; BUG-005 was previously Notion-only, backfilled 2026-09-04).
- **Capabilities/Skills/Rules:** 6 rows (CAP-001 through CAP-006, mirroring `CAPABILITY_REGISTRY.md`).
- **Owner Approvals:** 0 rows — nothing approved yet (every owner-reserved drill run to date tested a correct refusal, not an approved exception).
- **Model Routes and Agent Runs:** 2 rows (unchanged since 2026-08-31 — this is itself part of the F5-005 finding: most routed tasks since then have no MR-style evidence recorded here).
- Standalone page (not in a database): "Fresh-session CAP reuse proof - 2026-08-31".

## Reconciliation note

This is currently a one-way sync (knowledge/ -> Notion, written manually per session). No automated sync job exists yet. Any session updating `CURRENT_STATE.md` should also update the relevant Notion row(s) in the same turn where practical, and note here if it could not. **Known gap (F5-014):** prior to 2026-09-04, this file itself had not been updated since chunk 1, despite dozens of real rows being written in the interim — a session relying on this file alone (rather than live-querying Notion) would have reconstructed a badly stale picture. No process currently enforces keeping this file current; treat that as an open risk, not a solved one, even after this correction.

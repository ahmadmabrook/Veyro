---
doc: NOTION_CONTROL_PLANE
status: LIVE
updated: 2026-09-13 (Phase 9 restoration proof, fifth Gatekeeper pass Editorial — front matter date corrected; body's row-count section corrected 2026-09-13, fourth pass P1-3, four stale 2026-09-04 claims fixed)
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

## Rows written so far (per-line dates as corrected below; front matter and this section header stale prior to 2026-09-13, Phase 9 fourth Gatekeeper pass P1-3 and fifth pass Editorial — one line had repeated the exact "0 rows" falsehood already fixed once in `CURRENT_STATE.md` line 21)

- **Modules:** 1 row — MOD-000, Status=Certified (updated 2026-09-13, Phase 10 final approval — `notion-update-page` confirmed live), WIP Active=true, `Updated`=2026-09-13.
- **Scenarios:** 95 rows. **Corrected 2026-09-13 (Phase 10 readiness):** re-reconciled all rows live via SQL against the Phase 10-updated canonical matrix (`PHASE8_CANONICAL_95_MATRIX_2026-09-12.md`'s "Phase 10 update" section) — 6 rows flipped `Not started` → `Done` (SCN-087/088/089/091/093/084; SCN-094 was already correctly `Done`, a pre-existing catalog-vs-Notion inconsistency now resolved consistently). Post-update live verification: **82 `Done`, 13 `Not started`**, exact match to the canonical 82/8/3/2/0 matrix (supersedes the prior "76 Done / 19 Not started" reconciliation from Phase 8 chunk 27).
- **Test Runs:** grown well past the original 4 — new rows added through at least Phase 8 (`TR-MOD000-20260912-017`, `TR-MOD000-20260912-018`), each a real, dated record tied to its phase.
- **Bugs:** **re-corrected 2026-09-13 (Phase 10 readiness)** — a live SQL query this chunk returned exactly 1 non-`Done` row (BUG-010, Minor, owner-decision-pending by design), an exact match to `knowledge/05-QA/BUG_REGISTRY.md`; the database now has 27 bug rows total (BUG-001 through BUG-027). This chunk flipped BUG-025 to `Done` (fixed) and created BUG-027 (`Done`, accepted as a disclosed limitation, non-blocking).
- **Capabilities/Skills/Rules:** **corrected 2026-09-13** — 7 capabilities (CAP-001 through CAP-007) are registered and APPROVED per `CAPABILITY_REGISTRY.md`, not the 6 this line previously said (CAP-007 added 2026-09-08).
- **Owner Approvals:** **re-corrected 2026-09-13 (fifth Phase 10 certification round, P2-2)** — `OWNER_APPROVALS.md` durably records `OWN-001` (2026-09-05, vault migration), `OWN-002` (2026-09-13, EIP front-matter-vs-§21.1 adjudication, closing `EXT-01`), and `OWN-003` (2026-09-06, orchestrating-session model tier); the prior version of this line, itself already a correction, omitted `OWN-002` the same day it was recorded — this line's original "0 rows — nothing approved yet" was accurate only through Phase 4 and had gone stale, the same falsehood `CURRENT_STATE.md` line 21 independently carried until Phase 9's second Gatekeeper pass fixed it there.
- **Model Routes and Agent Runs:** 2 rows as of 2026-08-31 (this specific count not re-verified live this chunk — flagged, not silently carried forward as current).
- Standalone page (not in a database): "Fresh-session CAP reuse proof - 2026-08-31".

**This section is a point-in-time snapshot, not a live view** — the counts above describe the dates cited per line, most now corrected as of 2026-09-13. For current Notion state, run a live query against the relevant database rather than trusting this section's numbers past the date each line names.

## Reconciliation note

This is currently a one-way sync (knowledge/ -> Notion, written manually per session). No automated sync job exists yet. Any session updating `CURRENT_STATE.md` should also update the relevant Notion row(s) in the same turn where practical, and note here if it could not. **Known gap (F5-014):** prior to 2026-09-04, this file itself had not been updated since chunk 1, despite dozens of real rows being written in the interim — a session relying on this file alone (rather than live-querying Notion) would have reconstructed a badly stale picture. No process currently enforces keeping this file current; treat that as an open risk, not a solved one, even after this correction.

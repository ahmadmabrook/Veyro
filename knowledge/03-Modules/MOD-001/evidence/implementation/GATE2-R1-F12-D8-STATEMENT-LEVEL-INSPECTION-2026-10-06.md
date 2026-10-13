# R1-F12 · D8 statement-level accounting inspection

- UTC: 2026-10-05T22:08:02.688181+00:00; runner operation `d3a1b596-e92f-448b-b85f-6ce03f7987a8`; one local deterministic inspection, no Claude dispatch or source/test edit.
- Contract: ADR-011 D8 requires `zero-table triggered statements` in both text and JSON; D6.3 distinguishes table-free clean statements from unresolvable table positions. The current `_scan_sql_text` receives a whole `.sql` file as one text subject and increments `_ZeroTableCounts` once for that subject. Its own note explicitly discloses that this is **not statement-level accounting**.
- Synthetic fixture: `app/modules/membership/repo.sql`, manifest version 1, membership domain `MEM-01`, prefix `mem_`, real declared `app.modules.membership.interface`. Invoked `backend/.venv/bin/python tools/validate_architecture_gates.py --gate module-deps --modules-dir <temp>/app/modules --module-manifest <temp>/manifest.json --json` on each case; parsed `GateReport.notes` for the D6.3/D8 zero-table note.

| SQL file content | Actual CLI result | Actual D8 zero-table count | Literal per-statement count required before F12 can be claimed fixed |
|---|---|---|---|
| `SELECT 1; SELECT now()` | PASS/0, no violations | 1 recognised **subject**, 1 clean, 0 table-bearing | 2 recognised statements, 2 clean |
| `SELECT 1; SELECT id FROM mem_roster` | PASS/0, no violations | 1 recognised **subject**, 0 clean, 1 table-bearing | 2 recognised statements, 1 clean, 1 table-bearing |

The actual output truthfully says `subject(s)` and names the limitation; this is an **evidence of a remaining D8 obligation**, not a newly discovered silent PASS or a scenario failure. No CTE name was supplied to live attribution; state 3 remains unreachable. The qualified U1/U2 B HOLD forbids editing `_scan_sql_text`'s attribution loop, passing `cte_names` at the live call site, changing precedence, or otherwise making state 3 reachable. A bounded next code/test increment must isolate safe statement-boundary accounting from state-3 attribution and test at least the two cases above plus quoted/comment/dollar-quote semicolon controls; if this cannot be done without the held lexer semantics, seek a qualified decision instead of wiring `_cte_scopes` unilaterally.

Source SHA-256 `fc6404c613fb5f475fe7e7dd05f1efc5654833503f9294ef692694461cbed08d`; test SHA-256 `6f2c304e45594ab5e194aedf399a1aefc36649b78234e3f7c723f5608784184d`. F12 remains formally OPEN; other D8 file/prune-surface and positive evidence-set reconciliation, then combined independent round-2 code review, remain. No scenario promotion, review verdict or real-tree ownership claim.

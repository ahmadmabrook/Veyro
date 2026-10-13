# R1-F14 · SCN007 raw-table CLI evidence

- UTC: 2026-10-05T22:04:37.047870+00:00. Runner operation `3d6adbe4-3eb1-409e-9c1d-42771e62a54c`.
- Scope: **synthetic** `app/modules` tree only; membership `mem_`, billing `bil_` and schema `sb`. The importer is `membership/repo.sql`, with no cross-domain Python import. Exact manifest, fixture files, SQL strings, CLI command templates, text and JSON stdout/stderr/exit codes for every run are in `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-F14-RAW-TABLE-CLI-CAPTURE-2026-10-06.json`.
- CLI invocation (each case, both modes): `backend/.venv/bin/python tools/validate_architecture_gates.py --gate module-deps --modules-dir <temp>/app/modules --module-manifest <temp>/manifest.json [--json]`. The temporary path is generated per case.
- Exact replay from the durable capture: `backend/.venv/bin/python knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-F14-RAW-TABLE-CLI-REPLAY-2026-10-06.py` → **11 cases / 22 CLI invocations PASS**, comparing each exit code, complete stdout and stderr byte-for-byte. Replay script Ruff and compile PASS.

| Case | SQL in membership/repo.sql | Exit, text and JSON | Status | Code(s) |
|---|---|---:|---|---|
| `bare_cross` | `SELECT id FROM bil_invoices` | 1 | FAIL | CROSS_DOMAIN_SQL_IMPORT |
| `own_positive` | `SELECT id FROM mem_roster` | 0 | PASS | none |
| `public_qualified` | `SELECT id FROM public.bil_invoices` | 1 | FAIL | CROSS_DOMAIN_SQL_IMPORT |
| `uppercase` | `SELECT id FROM BIL_INVOICES` | 1 | FAIL | CROSS_DOMAIN_SQL_IMPORT |
| `three_part` | `SELECT id FROM db.sb.bil_invoices` | 2 | ERROR | MODULE_DEPS_TABLE_UNATTRIBUTED |
| `quoted` | `SELECT id FROM "bil_invoices"` | 1 | FAIL | CROSS_DOMAIN_SQL_IMPORT |
| `ddl` | `CREATE TABLE bil_shadow (id int)` | 1 | FAIL | CROSS_DOMAIN_SQL_IMPORT |
| `merge` | `MERGE INTO bil_invoices USING mem_roster ON true WHEN MATCHED THEN DELETE` | 1 | FAIL | CROSS_DOMAIN_SQL_IMPORT |
| `copy` | `COPY bil_invoices TO STDOUT` | 2 | ERROR | MODULE_DEPS_SOURCE_UNINSPECTABLE |
| `lock` | `LOCK TABLE bil_invoices` | 1 | FAIL | CROSS_DOMAIN_SQL_IMPORT |
| `grant` | `GRANT SELECT ON bil_invoices TO reader` | 2 | ERROR | MODULE_DEPS_SOURCE_UNINSPECTABLE |

The decisive raw-table negative returns `CROSS_DOMAIN_SQL_IMPORT`, subject `membership -> billing`, detail `membership/repo.sql: table 'bil_invoices' owned by 'billing'`, exit 1 in both text and JSON. The same-tree own-table `mem_roster` returns PASS/0 with no violation in both modes. `public.` qualification, unquoted uppercase, double quotes, DDL, MERGE and LOCK also return the named cross-domain FAIL. A 3-part name returns `MODULE_DEPS_TABLE_UNATTRIBUTED` ERROR/2, as ADR-011 D3.3 rule 1 requires; COPY and GRANT return `MODULE_DEPS_SOURCE_UNINSPECTABLE` ERROR/2 under D6.3's I-1 backstop. These are fail-closed outcomes, **not** additional `CROSS_DOMAIN_SQL_IMPORT` proofs.

The dedicated F14 test-only increment was independently verified at 523/523 tools tests with Ruff/compile PASS; see `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R1-F14-RAW-TABLE-TEST-VERIFICATION-2026-10-06.md`. Scanner source SHA-256 `fc6404c613fb5f475fe7e7dd05f1efc5654833503f9294ef692694461cbed08d`, test SHA-256 `6f2c304e45594ab5e194aedf399a1aefc36649b78234e3f7c723f5608784184d`. Capture SHA-256 `f1700397136cd24d98f282daf069afe55ea1b3f73482ebb53d7c9f1882534f0b`; replay script SHA-256 `39f4201c4e3f16fbcd7eb2013ff6a63cd888178a235e5963ec4ade31cbf89e32`. No scanner source, governing document, review claim, scenario status, or live CTE state-3 wiring changed in this increment.

**Disposition:** F14's missing raw-table test/evidence half is locally fixed and reproducible. Its formal round-1 ledger state remains OPEN until independent combined round-2 code review and subsequent scenario/security assurance address their separate criteria. This record is neither a review verdict nor SCN-MOD001-007 PASS; full application-tree ownership and still-unwired CTE state 3 are not inferred from synthetic fixtures.

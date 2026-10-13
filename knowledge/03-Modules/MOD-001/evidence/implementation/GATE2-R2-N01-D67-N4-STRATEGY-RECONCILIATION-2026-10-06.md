# R1-F01 / R2-N01 — D6.7 N4 post-N3 strategy reconciliation

Runner operation `1e44882c-afaf-4e89-b940-d6b28a627266`. Analysis-only, no Claude dispatch, source/test edit, review, or scenario verdict. The prior N3 guarded operation `69790653-9c7c-4af6-8636-50e1a104ef05` completed at exit 0 and was already reconciled; its evidence is `GATE2-R2-N01-D67-N3-REFERENCES-VERIFICATION-2026-10-06.md`. Source/test SHA-256 remain `291c4955928feea88fe5643e780f0304e431a61c8149c2072d7148b8c0f902d8` / `7ddbfc6eaf7259cb2a82a39a9909432192c204c05e7eedd3c21f6b2977717ebe`.

Governing contract refreshed and acknowledged for this operation; baseline verifier 4/4 PASS, all 11 expected governing-file hashes MATCH. Live ledger remains ACTIVE for MOD-001 GOV-01-R04 gate 2, R2 BLOCKED P0=1/P1=1/P2=2/P3=2, review claim CLEAR after the recorded BLOCKED R2. R04 projection is STAGNANT: three completed bounded operations since last original-finding blocker reduction. F03 is already locally verified, not a legal replay target. F01 is the one affected original finding and remains formally OPEN.

## Deterministic root-cause check

Using the same synthetic membership/billing fixture on the unchanged source:

| Row | Extracted identifiers | `.py` | `.sql` | D3.2 counts |
|---|---|---|---|---|
| N3 `CREATE TABLE mem_t (c int REFERENCES bil_invoices)` | `mem_t`, `bil_invoices` | FAIL/1 `CROSS_DOMAIN_SQL_IMPORT` | same | own=1, other=1 |
| N4 `DELETE FROM mem_t USING bil_invoices ...` | `mem_t` only | **false PASS/0** | same | own=1, other=0 |
| P4 `SELECT a FROM mem_x JOIN mem_y USING (id)` | `mem_x`, `mem_y` | PASS/0 | same | own=2, other=0 |

N3's new independent `REFERENCES` regex is a valid bounded N3 fix, but it did **not** replace `_scan_sql_text`'s statement-level `if not idents:` backstop with ADR-011 D6.7.2's per-position accounting comparison. The extractor and dangling checks still walk separate keyword sources, and `_TABLE_POSITION_KEYWORDS` still omits `USING`. Thus an own-domain `FROM` extraction suppresses any refusal for the unexamined `DELETE ... USING` target. Simply adding `USING` to another regex would repeat the keyword treadmill ADR-011 explicitly rejected; generic `USING (id)` in a JOIN is a column list, not a table position.

## Material strategy correction and next bounded increment

Replace the form-specific duplicated walks **for this active seam** with one shared table-position signal inventory consumed by both extraction and unresolved-signal accounting. Scope the next code/test increment to context-sensitive `DELETE ... USING` while retaining N3 and P4. Every recognised signal in the covered seam must resolve to an identifier carried to D3.2 or yield named `MODULE_DEPS_SOURCE_UNINSPECTABLE` ERROR even if an earlier `FROM`/`TABLE` position resolved. N4 `.py` and `.sql` must become exact `CROSS_DOMAIN_SQL_IMPORT` FAIL/1 with own=1/other=1; P4 stays PASS/0; N3 stays FAIL/1. A targeted mutant that drops the N4 signal or its attribution must be killed. Run focused tests, Ruff and compilation. Do not claim full D6.7: ONLY, other list positions, 10-row negative/5-row positive/7-mutant corpus, D8 completeness, and independent assurance remain.

This changes the implementation strategy from a succession of keyword-specific extractor patches to the ADR's shared signal/accounting mechanism, using the already-qualified Opus ADR decision; it changes no product architecture or owner-reserved domain binding. U1/U2 **B HOLD** continues to forbid live CTE state-3 wiring. No R3 review, scenario PASS, or certification is authorized by this analysis. Refresh at this material strategy boundary before the next dispatch.

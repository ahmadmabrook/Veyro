# Gate-2 R1-F01 / R2-N01 — D6.7.5 D8 lower-bound disclosure

Runner operation `1bb287a0-3904-457a-923e-8d755c28b0f0`, guarded routine implementation completed exit 0. Only `tools/validate_architecture_gates.py` and `tools/tests/test_validate_architecture_gates.py` changed, with durable code and test budget checkpoints. This is a local disclosure correction, **not** R1-F01 closure, a review verdict, scenario PASS, or permission to wire CTE state-3.

## Change and independent runner verification

`_d8_table_ref_note`'s completed-per-file-scan branch now says table-reference attribution figures are a **lower bound, not a total** because the run has no explicit ADR-011 D6.7.2 position-totality proof. It distinguishes completed file traversal from a proved complete table-reference inventory. The partial-scan and not-started branches remain distinct. No scanner decision, D3.2 counter, other D8 dimension, or result code changed.

After guarded exit, the runner independently executed `backend/.venv/bin/python -m pytest tools/tests -q`: **573 passed**; Ruff on the two changed files: **PASS**; `compileall`: **PASS**. Direct `_f12b_run` results, with both rendered note and `to_json()` note checked identical:

| Fixture | Status / code | D3.2 own / other / unattributed | Table-reference note |
|---|---|---:|---|
| own `SELECT` | PASS/0 | 1 / 0 / 0 | lower bound; no “complete” claim |
| billing `SELECT` | FAIL/1 `CROSS_DOMAIN_SQL_IMPORT` | 0 / 1 / 0 | lower bound; no “complete” claim |
| unknown-table `SELECT` | ERROR/2 `MODULE_DEPS_TABLE_UNATTRIBUTED` | 0 / 0 / 1 | lower bound; no “complete” claim |
| two files: own `SELECT` plus bare `TRUNCATE mem_t, bil_invoices` | ERROR/2 `MODULE_DEPS_SOURCE_UNINSPECTABLE` | 1 / 0 / 0 | lower bound; no “complete” claim |

The runner also injected an in-memory M-E6-like unconditional-complete note mutant and executed the mixed-file test: its report-text assertion **killed** the mutant. The guarded child reported a throwaway source mutant killed by the new text controls. Source SHA-256 `6031d5e193625a8c1c409fea05cad407752a6f4b2aa52a84367ec847a91341cf`; test SHA-256 `28e5e0135dbc226995f183dbe77e98cee579d2bd36e1d063e6110cb648bc7a70`.

## Boundary and residuals

The legacy F14 byte-exact CLI replay script failed on its historical stdout capture. The guarded child reconstructed the pre-this-increment note and found **0/22 exact output matches even before this change**, while expected exit codes matched; this is stale historical capture parity, **not** a passing replay and not evidence of a new D8 status regression. Neither its capture nor script was modified here. A future F14 evidence reconciliation must explicitly disposition that stale replay without rewriting history.

R1-F01 and R2-N01 P0 remain formally **OPEN**, R2 remains **BLOCKED**. `ONLY` still misattributes its keyword rather than the target table; bare TRUNCATE/COPY/GRANT forms yield no per-position records; the full N1–N10/P1–P5/M-E1–M-E7 corpus on both surfaces and DC-12 module-docstring correction remain; independent assurance has not run. U1/U2 **B HOLD** forbids live CTE state-3 wiring. No full review or scenario promotion is inferred.

# R2-N01 / R1-F01 — bounded D6.7 N3 REFERENCES verification

Operation: `69790653-9c7c-4af6-8636-50e1a104ef05` (`COMPLETED`, exit 0). One guarded Claude implementation dispatch. This is a local code/test increment, not independent assurance or formal finding closure.

## Change and observed result

`tools/validate_architecture_gates.py` now recognizes `REFERENCES` as an independent table-position signal in both identifier extraction and dangling-signal handling. The implementation does not widen `_TABLE_KEYWORD_RE`. It is a bounded N3 signal seam, **not** a completed shared D6.7 position-accounting system or a claim that all signal classes are covered. `tools/tests/test_validate_architecture_gates.py` pins N3, P4, and a dropped-extraction-loop mutant. The guarded child reported that the deliberate mutant killed the N3 and invariant tests, then reverted the temporary edit byte-for-byte.

Independent deterministic verification after child exit:

- `backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q`: **476 passed**.
- `backend/.venv/bin/python -m ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- `backend/.venv/bin/python -m py_compile` on both files: **PASS**.
- Direct fixture probe: N3 `CREATE TABLE mem_t (c int REFERENCES bil_invoices)` in `.py` and `.sql` is **FAIL/1**, `CROSS_DOMAIN_SQL_IMPORT`, own=1/other=1. P4 `JOIN mem_y USING (id)` in both forms remains **PASS/0**, own=2/other=0.
- Same direct probe: N4 `DELETE FROM mem_t USING bil_invoices ...` in `.py` and `.sql` remains **false PASS/0**, own=1/other=0. This is the exact unresolved next signal class.

Verified SHA-256: source `291c4955928feea88fe5643e780f0304e431a61c8149c2072d7148b8c0f902d8`; tests `7ddbfc6eaf7259cb2a82a39a9909432192c204c05e7eedd3c21f6b2977717ebe`.

## Boundary

R1-F01 and R2-N01 P0 remain OPEN/BLOCKED. N4 `DELETE ... USING`, ONLY, remaining D6.7 negative/positive/mutation corpus and D8 truthfulness remain; this N3 increment does not reduce the original-finding blocker set. Reconcile strategy at a refreshed contract boundary before another dispatch. U1/U2 **B HOLD** remains binding: live CTE state-3 wiring is forbidden. No R3 review, scenario certification, or PASS is inferred. The R2 review claim is CLEAR only because the prior BLOCKED result was recorded.

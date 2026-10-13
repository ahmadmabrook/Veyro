# R1-F01 / R2-N01 — ADR-011 D6.8 accounting and corpus completion (2026-10-06)

**Runner operation:** `38d1a3ed-726e-4ff5-9aac-c4edcb8d725e`. One guarded implementation operation completed with exit 0 and three material source/test checkpoints. This is local implementation evidence, **not** an independent review or scenario verdict. The preceding interrupted increment and its retained hashes are recorded in `GATE2-R2-N01-D68-INTERRUPTED-INCREMENT-LOCAL-RECONCILIATION-2026-10-06.md`.

## Scope and result

- D6.8.7 ordering precondition was observed before the changes: `_revoke_grantee_exclusion_offset` returned `None` on row 1A, and 1A failed with `CROSS_DOMAIN_SQL_IMPORT` on `.py` and `.sql`.
- The suppressible set is derived from the declared keyword patterns of the actual `_TABLE_POSITION_SIGNAL_SOURCES`, including the bound regex source. Its measured union is `{COPY, FROM, INTO, JOIN, ON, REFERENCES, TABLE, TRUNCATE, UPDATE, USING}`; the privilege intersection is `{REFERENCES, TRUNCATE, UPDATE}`. An undeclared or unparseable new source fails closed. An independent test adds a hypothetical `DELETE` source to prove the derivation changes; a hand-list regression is pinned.
- A run-wide sink aggregates suppressed signals and affected subjects. The D8 note is emitted on completed and error paths, including PASS and zero-suppression runs. A three-subject local probe observed 3 suppressed signals over 3 subjects. D6.7.5's table-reference **lower-bound** wording is retained.
- The full 25-row D6.8.9 matrix (P1–P9, N1–N14, 1A and 3A) executes on both `.py` literals and `.sql` files with fixture readback, exact status/exit/code assertions, D3.2 and suppression counts. The quoted `"ON"` N14 Python fixture uses a valid triple-quoted literal so it reaches the SQL scanner; both surfaces return `MODULE_DEPS_TABLE_UNATTRIBUTED` / exit 2. N3 is asserted as `CROSS_DOMAIN_SQL_IMPORT` / exit 1 naming `bil_invoices`; N10 stays `MODULE_DEPS_SOURCE_UNINSPECTABLE` / exit 2 via I-1.
- M-E8…M-E14 each have named executable controls. The guarded implementer reported a throwaway-copy drill killing all seven mutants, including both M-E14 variants, plus pre-D6.8 non-vacuity and pinned-identity drills; the throwaway copy was removed. The orchestrator independently reran the committed control tests, but the mutation drill's raw terminal log was **not retained as a separate artifact**. Independent round-3 assurance must inspect the mutation claims rather than treat this report as its verdict.

## Independent local verification

- `backend/.venv/bin/python -m pytest tools/tests -q`: **616 passed**. Architecture-gates file in guarded run: **543 passed**. The focused D6.8 controls: **16 passed** in the guarded run.
- `backend/.venv/bin/ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- `backend/.venv/bin/python -m py_compile` on both changed files: **PASS**.
- `backend/.venv/bin/mypy tools/validate_architecture_gates.py --no-incremental --show-error-codes`: **10 errors**, all at unchanged legacy locations (nine nullable-regex `.end()` accesses and one tuple assignment); no D6.8 new-line error was observed. This is not called a mypy pass.
- Final SHA-256 at this historical snapshot: source `b53808a2f7b8197578c2361d3553826193b28712e049a4e37b4e7d7abfaa9736`; tests `ee1f68b961843ea7eb34834abde5fa6603394da81818139668d01323dd8f6090`. The source value corrects a 62-character transcription error identified as R2-N06; it is the historical reviewed-snapshot hash, not the current source hash.

**Governed status:** R1-F01 is **locally fixed, awaiting independent assurance**, not formally closed. Round-2 BLOCKED remains the latest review verdict; no round-3 review was dispatched here. SCN-MOD001-006/-007/-095/-096 are unpromoted. U1/U2 **B HOLD**, its D8 coverage disclosure, and the prohibition on live CTE state-3 wiring are unchanged. WIP=1; MOD-002 locked. Evidence is **fixture-scoped; real-tree domain ownership DEFERRED**.

**Next legal boundary:** refresh the contract/governing snapshot, then assess readiness for one fresh independent round-3 code review under the existing review budget and a pre-written review claim. No PASS or formal finding closure is inferred from this local verification.

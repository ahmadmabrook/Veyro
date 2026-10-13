# R04 D6.8 assurance-entry evidence — 2026-10-06

**Scope:** MOD-001 GOV-01-R04 gate 2; fixture-scoped; real-tree domain ownership DEFERRED. This is deterministic local evidence, not an independent code-review verdict, formal finding closure, scenario PASS, or permission to wire held CTE state 3.

## Pinned snapshot

- Source `tools/validate_architecture_gates.py`: SHA-256 `b53808a2f7b8197578c2361d3553826193b28712e049a4e37b4e7d7abfaa9736` (before bounded operation: `8ad1136d896d58547fc59ee984c45b41a1b425019a575add976b595bfbe069e2`).
- Tests `tools/tests/test_validate_architecture_gates.py`: SHA-256 `ee1f68b961843ea7eb34834abde5fa6603394da81818139668d01323dd8f6090` (before bounded operation: `3327927734335a2aa70d239f89ef8df7d11a3064496cba7a4fe69a6b293c615f`).
- Bounded operation `38d1a3ed-726e-4ff5-9aac-c4edcb8d725e`: COMPLETED exit 0; source and tests changed, no evidence file emitted by the operation. This record supplies the missing deterministic evidence without another implementation dispatch.

## Review-entry criteria

1. **D8_ACCOUNTING — MET locally.** Run-wide `_SuppressionCounts` passes through `.sql`, string and bytes subjects to both completed and early ERROR paths. PASS/FAIL/ERROR report text and JSON disclose suppressed signals; a zero-suppression PASS discloses zero. D6.7.5's table-reference figure remains explicitly a lower bound. The three-subject aggregate 3/3 and two-signals-one-subject 2/1 controls pass.
2. **SOURCE_UNION — MET locally.** `_SUPPRESSIBLE_PRIVILEGE_SIGNALS` is derived from the actual signal-source keyword-pattern union intersected with PostgreSQL privilege vocabulary, currently `UPDATE/REFERENCES/TRUNCATE`; a hypothetical new `DELETE` source enters the set and an undeclared source fails closed. One pure suppression predicate is used at the sole `_table_position_results` merge point, with the object `ON` outside the open-end region.
3. **CORPUS_MUTATION_EVIDENCE — MET locally.** The finite 9 positive, 14 negative and two interaction rows execute on both `.py` and `.sql` surfaces with fixture readback, exact status/exit/code sets, attribution counts and suppression figures. The two identity pins pass. M-E8 through M-E14 were each actually injected, one change at a time, into a throwaway full-structure copy outside this repository and each selected control failed (7/7 killed); see `knowledge/03-Modules/MOD-001/evidence/implementation/GATE2-R2-N01-D68-MUTATION-RESULTS-2026-10-06.json`. A pre-D6.8 unsuppressed copy also made the own-domain positive control RED, demonstrating non-vacuity. No mutated copy was retained in the repository.

## Deterministic verification

- `backend/.venv/bin/python -m pytest -q tools/tests/test_validate_architecture_gates.py`: **543 passed**.
- `backend/.venv/bin/python -m pytest -q tools/tests`: **616 passed**.
- `backend/.venv/bin/python -m ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- `backend/.venv/bin/python -m py_compile tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- `mypy`: **not run**; no mypy result is claimed.
- Source/test hashes were checked after verification and match the pinned snapshot above.

**Assurance boundary:** the old combined round-2 review is BLOCKED on R2-N01. All 14 original R1 findings remain formally OPEN in the ledger despite local fixes and the old review's 13-of-14 code-level closure assessment. Next legal action is exactly one fresh independent code review on these hashes (chronologically round 3), then finding-by-finding reconciliation; only if no blocking code findings remain may the separate scenario/security assurance batch begin. U1/U2 B HOLD remains in force.

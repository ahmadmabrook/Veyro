# R1-F12 / ADR-011 D8 statement-level counting — bounded verification

Operation: `b7ad0e45-de14-4d51-8131-1bc999b9f810` (`R1-F12-D8-STATEMENT-LEVEL-CODE-TEST`). Guarded implementation completed with exit 0. This is local code/test evidence, **not** formal finding closure, combined review, or scenario certification.

## Change and observed result

- `tools/validate_architecture_gates.py` now cuts one SQL text subject into statement subjects only at lexically certain top-level semicolons. Its existing attribution body was moved unchanged into `_scan_sql_statement`; the live attribution call still passes no `cte_names`, and `_cte_scopes` remains unwired under the U1/U2 B HOLD.
- `tools/tests/test_validate_architecture_gates.py` pins `SELECT 1; SELECT now()` at 2 recognised / 2 clean and `SELECT 1; SELECT id FROM mem_roster` at 2 recognised / 1 clean / 1 table-bearing. It also pins semicolons inside quoted literals/identifiers, line/block comments and dollar-quoted bodies as non-boundaries, and a `SELECT 1; FROM` ambiguous cut as a retained dangling-keyword ERROR.
- The D8 note now discloses the lexical-certainty limit and decline-to-coarse-subject behavior. This increment does not assert universal SQL parsing or full D8 closure.

## Independent deterministic verification

- `backend/.venv/bin/python -m pytest tools/tests -q -p no:cacheprovider`: **529 passed**.
- `backend/.venv/bin/python -m ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- `backend/.venv/bin/python -m py_compile tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- Guard operation `ACTIVE_OPERATION.json`: `COMPLETED`, exit code `0`; both source and test files were material checkpoints.
- Source SHA-256: `c9d8f177f302d5be897edce1c25c0b0003d9a06409e3afebc63b837c618b4777`.
- Test SHA-256: `a6397a9054bf8290c5673ecc44e93e45b27b1d6961a06abfddb13ee848a2579c`.

## Remaining dependency and gates

R1-F12 remains formally OPEN. ADR-011 D8 full file/prune-surface accounting and positive evidence-set reconciliation are not yet verified, and combined independent round-2 review/scenario assurance remain pending. No live CTE state-3 wiring, review verdict, or scenario PASS is claimed. Next bounded action after contract refresh: deterministically inspect D8 full file/prune-surface accounting, then select one precise code/test or evidence-only increment from the observed gap; do not replay the verified statement-level increment.

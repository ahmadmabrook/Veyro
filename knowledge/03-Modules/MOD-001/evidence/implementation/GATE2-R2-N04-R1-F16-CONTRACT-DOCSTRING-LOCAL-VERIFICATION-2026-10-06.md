# R2-N04 / R1-F16 — bounded contract-docstring correction

Recorded: 2026-10-06T10:11:18.986026+00:00
Sole runner operation: `00d109dd-d406-4ec0-993e-32404d396d1f`. Classification: `MANDATORY_NOW` — the attested round-3 replacement review names both stale assertions as a P2 blocker, and ADR-011 D4 expressly requires correction of the `_shared` inversion. This is a local deterministic correction, **not** a fresh review, scenario verdict, or certification.

## Exact edit and snapshot

- In `tools/validate_architecture_gates.py`'s module docstring, corrected the direction: domain modules may import `_shared`; `_shared` importing domain internals or referencing an owned table is `CROSS_DOMAIN_SQL_IMPORT`. No scanner logic changed.
- Replaced “this gate's input contract is not yet fixed by an ADR” with the current ADR-011 contract, including D6.7/D6.8 addenda. No other source statement was intended to change.
- Source SHA-256: before `5eeac45f72ff613404c4b1918c9adbdd430675c0c26101d69725dd5b50c2c924`; after `1e8a170b855d1b71e1a0d50a10e608fcb127d3cf3fecedbd41a40c476833ef85`.
- Tests SHA-256 unchanged: `eb0088fa53a11d4111763ca967351fe64e535a83e41ff8af1f342b58f19f076b`. These files were already untracked in the existing worktree; `git diff` alone cannot show this increment.

## Deterministic verification

- `backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -p no:randomly -q`: **547 passed**.
- `backend/.venv/bin/ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- `backend/.venv/bin/python -m py_compile` on both files: **PASS**.
- Parsed module docstring assertions: corrected statements present, both stale assertions absent: **PASS**.
- Governing baseline verifier: 4/4 hashes matched before the edit; 11/11 refresh source hashes matched; contract refresh acknowledged for this runner operation.

## Limits and next dependency

R2-N04/R1-F16 is **locally corrected**, not independently assured. The round-3 review remains attested **BLOCKED**, and R1-F14 remains formally **OPEN** with its prior 22/22 capture pinned to an older source. R1-F19 pinned Ruff configuration and R2-N05/N06 evidence/projection directives remain. Reconcile those mandatory items, refresh/replay F14 evidence on the final source, then obtain only the minimum governed material-change and evidence-currency judgment. U1/U2 B HOLD forbids live CTE state-3 wiring; no scenario status, review counter, or MOD-001 exit state changed.

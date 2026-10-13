# R2-N01 D6.7.3 GRANT/REVOKE ON — bounded local verification (2026-10-06)

Runner operation `bfebe963-d03a-4104-bcac-a564f0b22a83`; guarded implementation subgoal `R04-GATE2-R2-N01-D67-GRANT-REVOKE-ON-NEXT-BOUNDARY`. Guarded child completed exit 0 with source and test material checkpoints. This is one R1-F01 code/test increment, not formal closure, an independent review, or scenario certification. U1/U2 B HOLD and the live CTE state-3 prohibition remain intact. No ADR/D8 disclosure or review/scenario state was edited.

## Verified effects

The source adds a context-sensitive GRANT/REVOKE object-`ON` signal to the existing `_TABLE_POSITION_SIGNAL_SOURCES` and routes `ON` through the single `_LIST_POSITION_SIGNALS` walk. The REVOKE grantee `FROM` exclusion is offset-based. Five new tests cover own/cross-domain GRANT and REVOKE targets, comma lists and `ONLY`, unresolved/dangling, and non-table/JOIN exclusions on `.py` and `.sql` surfaces. Older assertions pinned to the formerly absent signal were reconciled, not deleted. Four representative source/list/context/exclusion mutants were killed on throwaway `tools/` copies by named controls; see the guarded worker's completed operation transcript for individual failure traces. The committed working-tree source is still untracked WIP; no git promotion was performed.

Independent local run after child completion:

- `backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q --tb=line`: **524 passed**.
- `backend/.venv/bin/ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- `backend/.venv/bin/python -m py_compile tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- Source SHA-256 `50e86cca714db89484149bd64f3cb7079cef4b243fb9a4b6c4196597ea65fe9b`; test SHA-256 `13f61a4c997e3c872f84c371bfa1d6bd8d17a51ddc40cedca4e23e516c5dc965`.

Simple live fixture `GRANT SELECT ON bil_invoices TO r` and `REVOKE SELECT ON bil_invoices FROM r` now reach `CROSS_DOMAIN_SQL_IMPORT` FAIL exit 1 rather than an I-1 or grantee-as-table ERROR. The real-tree gate remains unavailable because `contracts/modules/ownership.json` is absent; fixture verification is not claimed as real-tree ownership assurance.

## Exact residuals — no closure

1. **Pre-existing privilege-as-signal collision, still live.** `GRANT UPDATE ON mem_roster TO r` emits both `UPDATE -> ON` (a spurious table position) and `ON -> mem_roster`; `GRANT REFERENCES ON mem_roster TO r` has the corresponding `REFERENCES -> ON`. A comma privilege/object list can also double-count the object continuation. The guarded worker compared a throwaway pre-increment source copy and found the spurious position already existed; this increment adds real target attribution beside it but does not remove the ERROR. The next code/test increment must context-scope those two older signal sources without masking any ordinary UPDATE/REFERENCES table positions.
2. **New unbounded REVOKE grantee-`FROM` lookahead in the unsplit position stream.** Independent white-box probe of `_table_position_results('REVOKE SELECT ON mem_roster; SELECT a FROM bil_invoices')` returned only `ON -> mem_roster`; the later ordinary `FROM -> bil_invoices` was excluded because `_revoke_grantee_exclusion_offset` searches for the first `FROM` anywhere after `ON` without stopping at the statement boundary. With an actual lexically certain semicolon, the dual-surface scanner splits and still returns FAIL exit 1 for the billing table; that specific live fixture is not a demonstrated false PASS. The shared position-stream invariant is nevertheless violated: an uncut/uncertain segment can lose an unrelated `FROM` without a positively computed grantee offset, contrary to ADR-011 D6.7.1's safe extraction direction. A bounded offset-boundary correction and explicit discriminating control are required before assurance. No PASS or review verdict is inferred from the 524 green tests.

R1-F01 remains formally OPEN, R2 BLOCKED. After these residual code/test blockers, ADR-011 D6.8 amendment and independent round-2 assurance remain. No full review while code/test blockers remain.

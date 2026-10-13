# R1-F12 / ADR-011 D8 namespace file/prune accounting — bounded verification

Runner operation `8b039122-7826-42e3-a72e-8c87c5680718`, guarded implementation subgoal `R1-F12-D8-NAMESPACE-FILE-PRUNE-COUNTS`: `ACTIVE_OPERATION.json` COMPLETED, exit 0, durable code and test checkpoints. This is local technical verification, **not** formal finding closure, independent review, or scenario certification.

## Bounded change

`tools/validate_architecture_gates.py` now records the non-discovered-namespace probe's inert files and `__pycache__` versus dot-directory prunes at the point each is observed. The D8 file note renders a third, traversal-specific group for these observations, separate from the top-level D5 listing and the discovered-module/`_shared` scan walk; it discloses the number of probes and early stops. A probe that aborts remains attempted and its counts are labelled minimum; a pass not entered reports UNKNOWN, not fabricated zeros. The D5 namespace-inert bucket, scan inclusion, violations, and verdicts remain unchanged. No live CTE state-3 wiring, `cte_names` input, or `_cte_scopes` call was added.

`tools/tests/test_validate_architecture_gates.py` adds ten focused namespace accounting tests covering inert-only, each prune reason, three disjoint prune territories, short-circuit, abort, complete/partial/UNKNOWN labels, text/JSON surfaces, unchanged verdicts, and the CTE hold. Superseded two-pair note assertions were updated to three-pair assertions.

## Independent deterministic verification

- `backend/.venv/bin/python -m pytest tools/tests -q -p no:cacheprovider`: **539 passed**.
- `backend/.venv/bin/python -m ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- `backend/.venv/bin/python -m py_compile tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: **PASS**.
- Replayed the preceding inspection's exact synthetic PASS fixture: `PASS`, exit `0`, no violations; old scan figures unchanged (`inspected=5`, `attempted=5`, `inert=0`, root=1, top/scan-walk prune pairs each 0), and the newly disclosed namespace group is `pycache=1`, `dot=1`, `inert=1`, `probes=1`, `short=0`. D5 still reports `namespace_inert=1`.
- Guarded worker additionally ran 466/466 focused tests and reported eight relevant mutants killed in an isolated `/tmp` copy; those are worker observations, not independent assurance.
- Source SHA-256: `b9e012a47a10935fc5dd390383b6907131c65be01372b5b02dc6d0b47e8e6484`.
- Test SHA-256: `83779ff7c49626be57200374024f4b262879d86291b4d3b116581c4b38ac0288`.

## Remaining dependency

R1-F12 remains formally **OPEN**. The D8 positive evidence set must still be reconciled against the report's non-vacuous coverage claims and governing ADR-011 before combined independent round-2 review. This increment does not infer a gate verdict, scenario PASS, or qualified permission to wire CTE state 3. The next bounded action after contract refresh is deterministic evidence-set inspection and one exact reconciliation outcome, not a replay of statement-level or namespace counter implementation.

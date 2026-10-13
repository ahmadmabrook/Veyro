# Gate-2 R1-F01 / R2-N01 — COPY tests-first RED increment

**Operation:** `570b0e80-1c4e-40b2-b497-b452cd425020`; subgoal `R04-GATE2-R2-N01-D67-COPY-DUAL-SURFACE-CONTROLS`. One guarded Sonnet test-author dispatch completed with a material test checkpoint. The qualified COPY direction decision remains the governing scope. This is test evidence, **not** a finding closure, review verdict, or scenario certification.

## Change and independent verification

- Added eight tests in `tools/tests/test_validate_architecture_gates.py` covering decision controls C-01..C-20 on `.py` literal and `.sql` surfaces, including D8 clean/unresolved accounting and the M-C8 signal-source position-order pin. Python SQL fixtures use `repr(sql)` to preserve quoting.
- Test file SHA-256: `4b7f9855dcc87daf83488c7da24f69cab3df474a487eee222ceed2050c998c3a` (was `b02713456d1fe616ee091a380cc6e0a08dd7e41b129046a8c463790fb4b91315`). Source file SHA-256 remained `cdff7e29a8380f42366e3de62cd0d6cc96b7929278a7419cabee6f99c0d0a3b7`.
- Local baseline run: `backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q -k 'not test_gate2_d6_7_copy_'` → **510 passed, 8 deselected**.
- Local new-controls run: `backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q -k 'test_gate2_d6_7_copy_' --tb=line` → **6 failed, 2 passed**, expected RED. Failures identify absent COPY target attribution (C-01/C-02), incorrect query-form zero-table treatment (C-07), quoted target yielding `STDIN` instead, mixed-form ERROR, and the not-yet-defined `_copy_table_position_matches` import. Two ordinary/undecidable non-regression controls pass on the unchanged source.
- `backend/.venv/bin/python -m ruff check tools/tests/test_validate_architecture_gates.py` and `backend/.venv/bin/python -m py_compile tools/tests/test_validate_architecture_gates.py` both pass.

**Finding result:** `FINDING_BLOCKED_WITH_EXACT_DEPENDENCY`. R1-F01 remains formal OPEN. The exact dependency is one atomic, qualified source increment adding COPY target-position emission **coupled with** context-sensitive suppression of only table-target COPY's top-level directional `FROM`/`TO`, then turning these RED controls green without regressing the 510 baseline tests. `COPY (SELECT 1) TO STDOUT` must become D6.3 clean zero-table; undecidable COPY remains ERROR. Do not wire live CTE state-3, replay D8 disclosure, or open a review yet.

# Gate-2 four-scenario current-snapshot local reconciliation — 2026-10-08

Operation: `d8133a03-3448-43b9-a968-18b8a00b5bef`. Classification: **MANDATORY_NOW**, shared GOV-01-R04 gate-2 scenario surface; no optional scope. This is local deterministic evidence following formal R1-F14 closure, not a new review, independent scenario/security assurance, or scenario PASS. No product source, tests, or pinned F14 capture were edited.

Pinned snapshot (SHA-256): scanner `1e8a170b855d1b71e1a0d50a10e608fcb127d3cf3fecedbd41a40c476833ef85`; tests `eb0088fa53a11d4111763ca967351fe64e535a83e41ff8af1f342b58f19f076b`; F14 CLI capture `cb3afd1aaed3fd44f8ff3604ee2cfd64135bb3c06d49d32b8351dc0d1874a2bb`. These match the one-off adjudication snapshot.

Command: `backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q -k 'test_scn006_own_schema_and_approved_interface_pass or test_scn007_cross_domain_raw_import_fails_citing_both_modules or test_scn007_raw_table_reference_is_denied_cross_domain_and_clean_for_own_table or test_scn095_bidirectional_pair_permitted_synchronous_direction_passes or test_scn096_bidirectional_pair_reverse_edge_denied'`

Observed result: `5 passed, 542 deselected in 0.10s` (exit 0).

| Scenario | Current-snapshot local evidence | Remaining boundary |
| --- | --- | --- |
| SCN-MOD001-006 | Own-table plus declared public-interface positive fixture passed. | Individual scenario reconciliation/assurance. |
| SCN-MOD001-007 | Raw import and raw SQL negative test passed; isolated raw-table negative/own-table positive pair also passed. F14 one-off independently adjudicated the pinned 22/22 CLI capture. | Independent scenario/security assurance; F14 closure alone does not confer scenario PASS. |
| SCN-MOD001-095 | All four declared §6.3 permitted synchronous directions passed in one test. | Individual scenario reconciliation/assurance. |
| SCN-MOD001-096 | All four reverse synchronous directions were denied with `REVERSE_EDGE_NOT_EVENT_DRIVEN` in one test. | Individual scenario reconciliation/assurance. |

Historical CLI fixture evidence is in `GATE2-VERDICT-C-SCENARIO-EVIDENCE-2026-10-05.md`; current tests above are the only new execution this operation. The scanner's disclosed static-analysis limits and ADR-011 U1/U2 **B HOLD** (no live CTE state-3 wiring) persist. Do not promote any of the four scenarios, certify GOV-01-R04/MOD-001, increment review counters, or infer a fresh reviewer entitlement from these five tests.

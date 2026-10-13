# R2-N01 D6.7 COPY mutation evidence — 2026-10-06

Operation: `92c81b92-93d7-4b7b-843c-8970cafe79cb`. Finding: `R1-F01` (formal OPEN). Scope: qualified COPY decision §5.1 M-C1..M-C8 only. This is local deterministic evidence, not a review verdict, ADR amendment, scenario certification, or closure.

The checked-in source was never mutated. Each mutant was constructed on a fresh, full `tools/` copy in an isolated temporary directory; the repository source and test hashes were checked after each process. The test module's `TOOLS` path resolved to that temporary copy. All mutant processes exited; temporary copies were removed. The exact probe and machine-readable results are `/tmp/veyro_copy_mutation_probe.py` and `/tmp/veyro_copy_mutation_results.json` (ephemeral supporting artifacts, not governance sources). The source baseline SHA-256 was `d2eb89d75f5df784f32767532d962af3699461c5a94240ecfea37fb537dc6bb0` throughout.

| Mutant | Applied change | Discriminating control and observed result |
|---|---|---|
| M-C1 | Omitted COPY signal source, retained direction exclusion | **KILLED**: C-01/C-02 extraction returned `[]` instead of `mem_roster`/`bil_invoices`; both surface-control tests failed. |
| M-C2 | Disabled balanced query-form exclusion | **KILLED**: C-05/C-06 produced two positions including unresolved `COPY` instead of the single inner-FROM position. |
| M-C3 | Removed `FROM` from `_TABLE_KEYWORD_RE` | **KILLED**: C-06 lost `bil_invoices`; C-09 ordinary `SELECT … FROM bil_invoices` returned ERROR instead of FAIL. |
| M-C4 | Suppressed every `FROM` when text contains `COPY` | **KILLED**: C-05/C-06 lost their inner `FROM`; the mixed position-order control also lost its ordinary `FROM`. |
| M-C5 | Disabled direction-offset exclusion | **KILLED**: C-03 extraction returned `['STDIN', 'mem_roster']`, not the one target. |
| M-C6 | Disabled COPY branch of `_has_bare_table_verb_form` | **Initially SURVIVED** C-08/C-19 end-to-end tests (2 PASS): the independent unresolved-position path masked this predicate defect. Added the positive table-target/dangling and negative balanced-query predicate control without weakening C-08/C-19. **KILLED on rerun**: the new predicate test failed on `COPY mem_roster TO STDOUT` (`False` versus required `True`); C-08/C-19 remained PASS. |
| M-C7 | Removed `COPY` from shared `_LIST_POSITION_SIGNALS` (single-target-walk surrogate) | **KILLED**: C-18 resolved `ONLY` rather than `mem_roster`. C-16 also ran and passed; the shared-list membership is independently pinned by C-18. This tests the routing seam, not every possible private COPY list implementation. |
| M-C8 | Moved COPY signal source before index-0 table-keyword source | **KILLED**: pinned position-order test failed on tuple order. |

The original seven killed-mutant runs used the prior 518-test snapshot; only M-C6 required a new control. The final repository test file hash is `6addde0615d917e87b5b2d074f28ec5bd8b89ff726cbd9ea241ea54c6ed42df9`. On final repository sources, `backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q --tb=line` returned **519/519 PASS**, and `backend/.venv/bin/ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py` returned **PASS**. The M-C6 rerun used this final test file on a fresh full `tools/` copy and failed only the new direct predicate control (1 failed, 2 passed, 516 deselected), so all eight representative mutants are now killed by a named control. Repository source hash remained unchanged.

Remaining exact dependency before R1-F01 can be fixed-awaiting-assurance or formally closed: the GRANT/REVOKE `… ON` table-position extraction gap in ADR-011 D6.7.3, followed by the D6.8 ADR amendment and independent round-2 assurance. Live CTE state-3 wiring remains forbidden under the U1/U2 B HOLD. R2 remains BLOCKED; no scenario or review promotion follows from this local evidence.

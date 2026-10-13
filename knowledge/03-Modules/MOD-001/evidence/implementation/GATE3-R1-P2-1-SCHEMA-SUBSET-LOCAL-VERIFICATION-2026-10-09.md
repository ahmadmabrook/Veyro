# Gate 3 R1 P2-1 — schema subset local verification

One guarded implementation under runner operation `b3464196-2fe4-4e29-90cf-bbae20d4ac1e` exited 0. The worker did not record `operation_budget.py` material-progress checkpoints because it looked inside the repository rather than using the absolute workspace-control path in the contract. This is a checkpoint-protocol defect, not evidence of no file changes: independent before/after SHA-256 comparison against the operation's pinned `trackedFiles` confirms all four scoped files changed. No reviewer, remote CI mutation, scenario promotion, or gate-2 reopening occurred.

- `tools/validate_architecture_gates.py`: `97fa9cef7b24` → `a9775193aab5` (changed: True)
- `tools/tests/test_validate_architecture_gates.py`: `598cb4abfc54` → `1b72350c8de4` (changed: True)
- `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md`: `05e5052bbcbe` → `dd13627c7196` (changed: True)
- `knowledge/03-Modules/MOD-001/SCENARIOS.md`: `41718dfa6523` → `23cb52b09ff8` (changed: True)

## Local correction and verification

`_event_entries` now validates both candidate and baseline event schemas before membership/diff can pass. The intentionally reduced, dependency-free vocabulary requires typed schema nodes and checks the documented forms of `properties`, `required`, `items`, `additionalProperties`, `enum`, `title`, and `description`; unknown/malformed/nested unsupported input, including the review's `{"x":1}` case, returns `EVENT_CONTRACT_GATE_INPUT_INVALID` (ERROR/exit 2) naming file, event and schema pointer. A valid object schema remains PASS in the synthetic test.

Independent runs: full architecture-gates test file **555/555 PASS**; scoped Ruff PASS; `py_compile` PASS; governing baseline hashes **4/4 MATCH**. The current live empty registry remains **INCONCLUSIVE/exit 2**, not PASS. The worker's disposable checker-disabled mutant made the new test fail; supplemental only, not independent assurance.

## Assurance boundary

This implements the qualified review's documented-reduction option **locally**, with an honest residual: it is not full JSON Schema meta-schema validation, it has no AsyncAPI document, and unsupported valid JSON Schema constructs fail closed. It validates keyword shapes but not applicability against `type`. P2-1 is **locally addressed, awaiting independent current-snapshot judgment**, not formally closed. P1-1/P1-2 also await assurance; P2-2..P2-4 remain open. The one gate-3 review entitlement is consumed. SCN-008/019/130 and SCN-020 are not promoted; MOD-001 exit remains 0/8; R1-F01..F14 remain formally 14/14 CLOSED for gate 2.

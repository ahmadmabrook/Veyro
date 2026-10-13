# Gate 3 R1 P1-2 — withdrawal approval-intent local verification

Operation `18071971-eefd-4221-b6aa-4da57f5f7650` completed one guarded implementation on the exact validator, test, IMPLEMENTATION, and SCENARIOS files. A preceding operation under `41c3b9e4-5349-4f8a-a03c-44eba84fc28a` failed before the Claude turn (`claude_code_version_too_old`), changed no tracked file, and was reconciled. The locally scoped ACPX adapter 0.88.0 resolved that transport failure; this operation returned exit 0. No second writer, reviewer, remote mutation, scenario promotion, or gate-2 reopening occurred.

## Corrected defect

A candidate event withdrawal now requires a candidate-side `removals.<event>=OWN-NNN` citation to exactly one live 5-column `OWNER_APPROVALS.md` row whose *Action approved* cell explicitly approves withdrawal/removal of that exact event. Introduction-only, unrelated event, scope-only, negated withdrawal, malformed row, and re-use of the baseline entry's own approval deny as `EVENT_REMOVED_UNAPPROVED` (FAIL/exit 1). Accepted-baseline tombstone continuity and its input-invalid ERROR/exit 2 rules remain. The registered-event change path remains unchanged.

## Independent deterministic verification

- `uv run --no-project --with pytest python -m pytest -q tools/tests/test_validate_architecture_gates.py`: **554 passed**. The new synthetic test includes the exact formerly false-green row `Approve introduction of event gone only; withdrawal is not approved`, an introduction-only row without negation, unrelated-event and scope-only rows, negation variants, malformed shape, and explicit-withdrawal positives.
- `uv run --no-project --with ruff ruff check tools/validate_architecture_gates.py tools/tests/test_validate_architecture_gates.py`: PASS. `python3 -m py_compile` on both: PASS.
- `backend/.venv/bin/python knowledge/00-System/verify_baselines.py`: **4/4 MATCH**.
- Worker also ran a disposable mention-only mutant: the removal tests rejected it. This is supplemental, not an independent assurance verdict.

## Boundary

P1-2 is **locally fixed and deterministically verified, awaiting independent assurance**. The single owner-authorized gate-3 independent review was already consumed on an earlier BLOCKED snapshot; this operation does not create a review entitlement. P1-1 is likewise locally verified awaiting assurance. P2-1..P2-4 remain open. SCN-008/019/130 and SCN-020 are not promoted; MOD-001 exit remains 0/8; gate-2 R1-F01..F14 stay formally 14/14 CLOSED. This fixed-phrase rule reads the register text, not proof of the owner's authorship or decision, and can refuse benign negated clauses (fail-closed). The change path still has mention-only semantics, disclosed separately; no claim is made for it here.

# M1-C-02 gate-6 source applicability and focused replay — 2026-10-09

Sole runner `b6d46ed7-b5c7-436c-add6-b179ff3824a9`; C02 **in progress**, not completed. This is an in-operation technical reconciliation, not a new planned unit or a review.

## Governing interpretation

- TSD §24.1 (TSD_MIRROR.md 11643–11653) specifies six comparisons across its 57 conceptual §10 domains. MOD-001 REQUIREMENTS.md 254–257 expressly excludes actual domain-contract content for domains that do not yet exist and assigns that content to later modules, while lines 258–266 require MOD-001 to build the non-trivial validator and a pipeline dry-run whose not-yet-applicable stages correctly skip. IMPLEMENTATION.md 350 says the domain lint runs on every push/PR **once >1 domain exists**, against the **full committed contract set**.
- The source-grounded MOD-001 path is therefore to prove the complete validator and SCN-014/015/131 with explicit disposable synthetic contract inputs, and wire an honest CI stage that denies invalid present contract data and records not-applicable only when no committed applicable contract set exists. Do not create a fabricated 57-domain document, claim that six backend scaffolds supply all 57 contract contents, or turn missing input into a generic PASS. When real domain contracts are committed by their owning modules, the CI path must use the full committed set and fail closed on missing/incomplete input. The exact applicability guard and trusted CI implementation remain **mandatory pending** in C02; no live CI claim yet.
- Qualified gate-6 D1–D5 decision and ADR-013 explicitly constrain the current input to synthetic fixtures and keep real ownership declarations and fidelity out of this increment. This interpretation does not waive TSD §24.1 enforcement when real input becomes applicable. No owner/product choice is made or requested here.

## Current deterministic evidence

- Eight shared focused controls in `tools/tests/test_validate_architecture_gates.py` passed (8/8, 623 deselected): disjoint six-dimension positive; independent RB-ID, identical-command-inventory, published-event and foreign-SLO-signal denials; matching exception positive, wrong-pair denial and denied-approval denial. These are **fixture-level component proofs**, not full SCN-014/015/131 execution or qualified assurance.
- Direct default `python3 tools/validate_architecture_gates.py --gate domain-uniqueness --json` returned ERROR/exit 2, `DOMAIN_UNIQUENESS_GATE_INPUT_INVALID`, because `contracts/domains/domain-contract.json` is absent. This is fail-closed but not an implemented CI applicability decision.
- C02 still owes a candidate-inert trusted CI stage with explicit applicability and full-set check, shared scenario execution with individual dispositions, and later R04 qualified assurance. All three scenarios remain NOT EXECUTED; gate-6 review/remediation 0/0; MOD-001 exit 0/8; R04 gate-2 F01–F14 14/14 CLOSED. No review entitlement inferred or consumed.

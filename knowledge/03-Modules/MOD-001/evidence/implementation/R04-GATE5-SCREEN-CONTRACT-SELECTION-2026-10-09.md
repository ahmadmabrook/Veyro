# R04 gate 5 — bounded mandatory-surface selection (2026-10-09)

Operation: `6ad91322-730d-4b5b-8fc9-1e53630dbaa0`. This is a read-only selection, not an active-slice switch, implementation, scenario verdict, or review entitlement.

## Governing need and observed state

- `REQUIREMENTS.md` GOV-01-R04 requires all TSD §24.1 architecture gates, each with a valid fixture and deliberate-violation denial; `IMPLEMENTATION.md` §4 gate 5 requires a Screen ID mapped to a BFF/read-model or typed command manifest row, and `UNMAPPED_SCREEN_CONTRACT` for an unmapped ID.
- `SCENARIOS.md` SCN-MOD001-012/013/110 are one shared gate-5 batch: mapped positive, unmapped-ID denial, and independently required canonical-registry-vs-generated-manifest **count-mismatch** denial citing expected and actual counts. All three are NOT EXECUTED. The catalog explicitly notes MOD-001 owns zero real screens; synthetic fixtures are appropriate for this gate, not a real-screen product expansion.
- Fresh read-only command: `backend/.venv/bin/python tools/validate_architecture_gates.py --gate screen-contract --json` returned exit **2**, `status: ERROR`, `GATE_NOT_IMPLEMENTED`, subject `screen-contract`. This is not PASS or a test of an implemented validator.

## Lean classification and next bounded unit

`MANDATORY_NOW`: one exact screen-contract validator/fixture unit, followed by deterministic positive and both negative executions. Omission leaves a named GOV-01-R04/TSD gate unimplemented and blocks R04 and MOD-001 certification; legal deferral is **no**. Keep the implementation within existing architecture-gates CLI and the minimum canonical screen count plus screen/BFF-command manifest input contract. Do not create a generic UI registry or implement later-module screens. CI workflow integration, live bypass proof, independent code/security/scenario assurance, and individual scenario promotion are later separate gates, not outcomes of this selection.

Scope-expansion check: the existing HIGH tier and 14-operation adoption baseline remain unchanged; the alert is active. This is an underestimated known mandatory R04 surface, not optional expansion. The four scope questions above justify one added bounded operation; the current mandatory remainder remains **unknown** because R01..R08, 140 scenarios, SCN-070 cap, manual/regression/Gatekeeper gates are not yet reconciled. No optional item is adopted. Four existing deferred items retain their named future owners. Review counters and the consumed gate-3 review authority do not change.

The 18 previously recorded additions were checked by ID and governing reason in `LEAN_EXECUTION_STATE.json`: five are R04 gate-3/SCN-020 minimum input and trusted-enforcement work, seven are concrete P1-1/P1-2 review-blocker diagnosis/remediation, and six are concrete P2-1..P2-4 review-blocker correction/proof. Each remains `MANDATORY_NOW` because omission leaves a required gate unimplemented or an observed false-green/blocking review finding; none is a confidence review or optional product expansion. This gate-5 selection is the nineteenth addition and is distinct from gate 3. The earlier scope-review evidence remains historical; this current check covers the observed 67 completed operations since adoption without resetting the baseline or inventing a completion estimate.

## Boundaries preserved

The active convergence unit remains R04 gate 3 until a governed slice switch after contract refresh. Upstream P2-4 PR #3 stays ready but REVIEW_REQUIRED/BLOCKED; upstream main is unchanged. R1-F01..F14 remain 14/14 formally closed for gate 2 only. SCN-012/013/110 remain NOT EXECUTED. U1/U2 B HOLD still forbids live CTE state-3 wiring. No reviewer, second writer, PR merge, protection bypass, or scenario promotion occurred.

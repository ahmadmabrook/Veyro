# Gate-3 P1-1 input-contract ADR decision dispatch

- Sole runner operation: `4da17026-3e88-4c61-8484-52998ff8cb2d`; no new runner, product writer, reviewer or review entitlement.
- Class: `MANDATORY_NOW` within MOD-001 HIGH, one bounded architecture/ADR judgment. TSD §24.1 and SCN-019 prohibit a false-green unregistered event. The prior root-cause artifact documented a dynamic-callee false PASS and an in-tree cross-file re-export escape; the first alias correction remains partial.
- Why now: the proposed emitter-escape contract would reverse an existing alias-positive fixture and add ERROR outcomes. Before implementation, a qualified architecture decision must settle whether this is a conforming, non-material gate-input contract or an owner-reserved architecture change; reject any claim that a review retry is authorized.
- Source: `knowledge/03-Modules/MOD-001/evidence/implementation/GATE3-R1-P1-1-DYNAMIC-CALLEE-ROOTCAUSE-2026-10-09.md`, especially §§5, 7, 8, 12, 13. The prior guarded operation ended SOFT_NO_PROGRESS/42 after writing that artifact, independently reconciled; it did not produce code or assurance.
- Primary outcome: one fresh-context Opus `veyro-lead` decision and concise ADR-012 only if within engineering authority. If DC-16 applies, write a narrow BLOCKED decision instead; do not edit validator, tests or workflow.
- No scenario promotion. Gate-3 review consumed, P1-1/P1-2/P2 remain open, F14 formally closed, MOD-001 exit 0/8.

# R04 gate 6 — mandatory unit selection and activation

Sole runner operation `915844ee-f9d3-44f0-9bd1-56189c140a62`. Control-plane selection only: no product code/test change, Claude dispatch, review, scenario verdict, or module credit. The runner lease was live, prior guarded operation completed, convergence ACTIVE, review claim CLEAR, contract refresh acknowledged, and four governing baselines matched.

## Scope and observed failure

**MANDATORY_NOW**: GOV-01-R04 and TSD §24.1 require domain-contract uniqueness lint as a CI-blocking gate across the 57 §10 domains. It compares normalized authoritative-entity sets, command inventories, published-event sets, runbook IDs, SLI/SLO signal names, and failure/degraded-behavior vocabulary. Identical command inventories or reused RB IDs require an approved pair-specific shared-contract exception; foreign-domain SLI/SLO and failure vocabulary require owned signals or documented dependency. MOD-001 `IMPLEMENTATION.md` §4 and `SCENARIOS.md` SCN-014/015/131 require one shared valid/negative/exception batch with individual dispositions.

The live `backend/.venv/bin/python tools/validate_architecture_gates.py --gate domain-uniqueness --json` returned `ERROR/GATE_NOT_IMPLEMENTED`, exit 2. `contracts/` currently contains event registry/baseline and UI screen registry only; no domain inventory or shared-exception register was observed. Thus no gate or scenario PASS is inferred. The authoritative TSD domain descriptions exist, but an exact normalized machine input contract still needs a bounded source/normalization decision before implementation. In particular, the two free-form entity/failure-vocabulary dimensions cannot be silently dropped or claimed proven by four structured-ID fixtures.

Lean four questions: the exact requirement is TSD §24.1/GOV-01-R04; omission leaves an unimplemented CI gate; this blocks R04/MOD-001 certification; legal deferral of the final gate is **no**. It is sequenced now because gate 5 needs absent per-screen route/API source authorities, while gate 6 can be advanced as a distinct mandatory unit. No optional scope or extra assurance round is added. Tier HIGH, initial 14 operations and historical counters retained; remaining MOD-001 mandatory operations unknown.

## WIP boundary

Gate 5 is **held, not closed**: real canonical 170-ID registry and validation-only mapping diagnostics remain; full authoritative screen manifest, route/API inputs, CI enforcement, independent assurance and scenario promotion remain pending. Its 0/0 review/remediation counts and three executed-but-unpromoted mechanical scenarios are archived unchanged. Gate 3's consumed review/P2-4 approval-assurance hold, gate 2's F01-F14 14/14 formal closure, SCN-070 five-review cap, U1/U2 B HOLD and MOD-001 0/8 exit remain unchanged.

Gate 6 is the sole active distinct work unit with 0/0 review/remediation counts and SCN-014/015/131 NOT EXECUTED. Next legal action after the new boundary refresh: make one bounded source/normalization decision for all six dimensions and the approved-exception register, then only the minimum validator/fixture implementation. No review entitlement follows from activation.

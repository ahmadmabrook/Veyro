# Gate-3 shared SCN-008/019/130 execution — 2026-10-08

Under sole runner operation `1e3b12e6-b565-4e58-9bec-e2eb783e93a9`, the MANDATORY_NOW shared gate-3 scenario batch ran **4/4 disposable CLI cases** against unchanged `tools/validate_architecture_gates.py` SHA-256 `28f3c458e2aae6e2243bfc749388e4f1d540dce1c410cc99671d78c9914d0ce4` and tests SHA-256 `de3e64ee9e32fbbafe653a2697fdb91ee9b907b63a2564a1a9ce86c9434e892b`. Structured input/output capture: `GATE3-EVENT-CONTRACT-SHARED-SCENARIO-CAPTURE-2026-10-08.json`. The fixture tree and `OWNER_APPROVALS.md` copy existed only inside a `TemporaryDirectory`; the live approval register was not changed.

| Required scenario | Direct observed result | Individual disposition |
| --- | --- | --- |
| SCN-MOD001-008 | Registered literal event returned `PASS`, exit 0, one checked subject | **EXECUTED — PENDING INDEPENDENT SCENARIO/SECURITY REVIEW**, not PASS |
| SCN-MOD001-019 | Unregistered referenced event returned `FAIL`, exit 1, `UNREGISTERED_EVENT_CONTRACT` naming the event | **EXECUTED — PENDING INDEPENDENT SCENARIO/SECURITY REVIEW**, not PASS |
| SCN-MOD001-130 | Changed schema adding a required field with no approval returned `FAIL`, exit 1, `EVENT_CHANGE_UNAPPROVED` naming the event and schema diff; identical change with disposable matching `OWN-999` row returned `PASS`, exit 0 | **EXECUTED — PENDING INDEPENDENT SCENARIO/SECURITY REVIEW**, not PASS |

This is deterministic execution, not independent Opus/security judgment or artifact/risk-required code review. The real repository still lacks `contracts/events/registry.json`, so the default live gate reports input ERROR and no production CI-gate readiness is inferred. The shared source file changed since the historical gate-2 F14 review, but F14's formal historical closure is not reopened; gate-2 scenario/security assurance remains separate. No review round or replacement authorization was consumed, and no scenario or module certificate was promoted. MOD-001 exit stays 0/8; U1/U2 B HOLD and SCN-070 review cap remain.

# Gate-3 event-contract mandatory surface selection — 2026-10-08

Runner operation: `bca4eeb9-a0ea-4cdb-b5a2-79264759239b`. This is a **MANDATORY_NOW** read-only slice selection, not implementation, a review, or a gate/scenario verdict. The active module remains MOD-001 under its sole writer lease; gate-2 F14 is formally closed, while SCN-006/007/095/096 remain executed but unpromoted pending separate scenario/security judgment.

## Scope decision

1. **Governing requirement:** GOV-01-R04 requires each TSD §24.1 architecture gate as a real CI-blocking check with valid and deliberate-violation proofs. The implementation plan's gate-3 row requires event references to resolve in the AsyncAPI/JSON-Schema registry and compatibility/classification changes to carry a matching owner-approval reference.
2. **Observed failure if omitted:** `backend/.venv/bin/python tools/validate_architecture_gates.py --gate event-contract --json` exited **2**, with `status: ERROR`, `GATE_NOT_IMPLEMENTED`, and `checked: []` on 2026-10-08. The real `contracts/`/`backend/app/contracts/` registries are absent; no real gate-3 PASS is possible today.
3. **Certification dependency:** One shared bounded gate-3 implementation surface must cover SCN-MOD001-008 (registered event positive), SCN-MOD001-019 (unregistered event denial), and SCN-MOD001-130 (unapproved compatibility/classification change denial plus disposable synthetic-approval positive). Code-bearing work would require deterministic fixtures and its own governed bounded review; this selection grants neither review entitlement nor scenario PASS. SCN-018/073 are broader API/schema-compatibility checks and are not silently folded into this gate-3 semantic unit.
4. **Deferral:** Not legally deferrable from MOD-001 certification because GOV-01-R04 and all three named Required scenarios remain unmet. Optional registry frameworks, future-domain event inventories, and unrelated gate implementations are outside this slice.

**Next boundary:** Refresh the mission contract at the changed requirement/slice boundary. Then activate exactly this distinct gate-3 unit in the convergence/control index, preserving gate-2's 3 normal review rounds, consumed replacement and one-off F14 adjudication as historical counters. No product edit, Claude writer, or reviewer was started by this selection. U1/U2 B HOLD still forbids live CTE state-3 wiring.
